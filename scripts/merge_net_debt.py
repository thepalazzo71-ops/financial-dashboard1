"""Merge the Europe net-debt research (WebSearch rounds, see docs/handoff-brief.md) into data/net_debt.json
and compute Enterprise Value = market cap (current, USD) + net debt (converted to USD).

Tiers:  A = gross debt AND cash found for the same balance sheet  -> net debt = gross debt - cash (leases separate)
        B = only the company-REPORTED net debt (definition varies: see 'definition' note)
Region: Europe (default, data/) or USA & Canada ('--region us', data-us/, status 'reported_only' = tier B, CAD supported).
Not computed: financial companies (banks/insurers), not-found, and balance sheets older than STALE_BEFORE.
Informational only - nothing here changes the v6 score.   Usage: python3 scripts/merge_net_debt.py <research_dir>
"""
import json, sys, glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGION = 'europe'
CFG = {'europe': {'dir': 'data', 'pool': 'companies_1000_scored.json', 'globs': ['nd[123]_out_*.json', 'ndp2_out_*.json']},
       'us': {'dir': 'data-us', 'pool': 'companies_pool_all.json', 'globs': ['ndus[123456]_out_*.json']}}
OUT = ROOT / 'data' / 'net_debt.json'
STALE_BEFORE = '2025-06-30'
# USD per 1 unit of currency. APPROXIMATE: ECB euro reference rates, EURUSD 1.1383 (1 Jul 2026);
# SEK/NOK/CHF/PLN crosses from 14 Jul 2026, DKK 1 Jul 2026, RON/ISK 4 May 2026. Replace with fresh rates and re-run.
EURUSD = 1.1383
FX = {'USD': 1.0, 'EUR': EURUSD, 'GBP': round(EURUSD / 0.85973, 4), 'SEK': round(EURUSD / 11.036, 5),
      'NOK': round(EURUSD / 11.077, 5), 'CHF': round(EURUSD / 0.9257, 4), 'PLN': round(EURUSD / 4.3383, 5),
      'CAD': round(1 / 1.4196, 5),  # Bank of Canada USD/CAD 1.4196 on 15 Oct 2026
      'DKK': round(EURUSD / 7.4745, 5), 'RON': round(EURUSD / 5.1977, 5), 'ISK': round(EURUSD / 143.6, 6)}
FX_NOTE = 'Approximate ECB reference rates from May-July 2026 (see merge_net_debt.py); +/-3% error on the net-debt part of EV.'


def num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def apply_overrides(entries, mc_o, byt):
    """Manual corrections (data/net_debt_overrides.json) applied on top of the researched figures; recomputes the derived fields."""
    path = ROOT / CFG[REGION]['dir'] / 'net_debt_overrides.json'
    if not path.exists():
        return 0
    n = 0
    for t, o in json.load(open(path)).items():
        if t.startswith('_') or t not in byt:
            continue
        cur = o['currency']; fx = FX[cur]
        gd, cash, rep, lease = num(o.get('gross_debt')), num(o.get('cash')), num(o.get('net_debt_reported')), num(o.get('lease_liabilities'))
        nd = gd - cash if gd is not None and cash is not None else rep
        mc = (mc_o.get(t) or {}).get('mc') or byt[t].get('mc0')
        e = {'tier': 'A' if gd is not None and cash is not None else 'B', 'currency': cur, 'balanceSheetDate': o.get('balance_sheet_date'),
             'periodType': o.get('period_type'), 'grossDebt': gd, 'cash': cash, 'leaseLiabilities': lease, 'netDebtReported': rep,
             'netDebt': round(nd, 2), 'netDebtUsd': round(nd * fx, 1), 'fx': fx, 'minorityInterest': None,
             'mcUsd': round(mc, 1) if mc else None, 'evUsd': round(mc + nd * fx, 1) if mc else None,
             'sourceUrl': o.get('source_url'), 'sourceType': o.get('source_type'), 'notes': (o.get('notes') or '')[:600],
             'flags': ['manual correction'] + (['balance sheet older than Q1 2026'] if (o.get('balance_sheet_date') or '') < '2026-03-31' else [])}
        if lease is not None and mc:
            e['evInclLeasesUsd'] = round(mc + nd * fx + lease * fx, 1)
        if o.get('ltm_net_income_local') is not None:
            e['ltmNetIncomeUsd'] = round(o['ltm_net_income_local'] * fx, 1)
            e['ltmNetIncomeNote'] = o.get('ltm_net_income_note')
        entries[t] = e
        n += 1
    return n


def main(rdir):
    rdir = Path(rdir)
    D = ROOT / CFG[REGION]['dir']
    comp = json.load(open(D / CFG[REGION]['pool']))
    byt = {c['ticker']: c for c in comp}
    mc_o = json.load(open(D / 'mc_overrides_applied.json'))
    rows = {}
    files = []
    for g in CFG[REGION]['globs']:
        files += sorted(glob.glob(str(rdir / g)))
    for f in files:
        for t, v in json.load(open(f)).items():
            rows.setdefault(t, []).append((Path(f).name, v))
    entries, stats = {}, {}
    for t, lst in rows.items():
        c = byt.get(t)
        if not c:
            continue
        mc = (mc_o.get(t) or {}).get('mc') or c.get('mc0')
        best = None
        if REGION == 'us' and c.get('is_financial_sector'):
            best = ('financial', {}, 'F')
        for fname, v in lst:
            st = v.get('status')
            if best is not None and best[0] == 'financial':
                break
            if st == 'financial_na':
                best = ('financial', v, 'F'); break
            gd, cash = num(v.get('gross_debt')), num(v.get('cash'))
            rep = num(v.get('net_debt_reported'))
            cur = v.get('currency')
            date = v.get('balance_sheet_date') or ''
            if cur not in FX:
                continue
            cand = None
            if st == 'ok' and gd is not None and cash is not None:
                cand = ('A', v, gd - cash)
            elif rep is not None and st in ('ok', 'not_found', 'reported_only'):
                cand = ('B', v, rep)
            if cand and date >= STALE_BEFORE:
                if best is None or (cand[0] == 'A' and best[2] != 'A'):
                    best = (cand[2], cand[1], cand[0])
        if best is None:
            stats['none'] = stats.get('none', 0) + 1
            continue
        if best[0] == 'financial':
            entries[t] = {'tier': 'F', 'status': 'financial_na'}
            stats['F'] = stats.get('F', 0) + 1
            continue
        nd, v, tier = best
        cur = v['currency']; fx = FX[cur]
        lease = num(v.get('lease_liabilities')); mi = num(v.get('minority_interest')); rep = num(v.get('net_debt_reported'))
        nd_usd = nd * fx
        e = {'tier': tier, 'currency': cur, 'balanceSheetDate': v.get('balance_sheet_date'), 'periodType': v.get('period_type'),
             'grossDebt': num(v.get('gross_debt')), 'cash': num(v.get('cash')), 'leaseLiabilities': lease, 'netDebtReported': rep,
             'netDebt': round(nd, 2), 'netDebtUsd': round(nd_usd, 1), 'fx': fx, 'minorityInterest': mi,
             'mcUsd': round(mc, 1) if mc else None, 'evUsd': round(mc + nd_usd, 1) if mc else None,
             'sourceUrl': v.get('source_url'), 'sourceType': v.get('source_type'), 'notes': (v.get('notes') or '')[:400]}
        if lease is not None:
            e['evInclLeasesUsd'] = round(mc + nd_usd + lease * fx, 1) if mc else None
        flags = []
        if tier == 'A' and rep is not None and abs(nd - rep) > max(0.15 * abs(rep), 3):
            flags.append('computed net debt differs from company-reported figure (definition?)')
        if v.get('source_type') == 'aggregator':
            flags.append('aggregator source')
        if tier == 'B':
            flags.append('company-reported net debt only')
        if mc and abs(nd_usd) > 3 * mc:
            flags.append('net debt > 3x market cap - check units/currency')
        if (v.get('period_type') == 'quarter' or (v.get('balance_sheet_date') or '') < '2026-03-31'):
            flags.append('balance sheet older than Q1 2026')
        e['flags'] = flags
        entries[t] = e
        stats[tier] = stats.get(tier, 0) + 1
    if REGION == 'us':
        for t, c in byt.items():
            if c.get('is_financial_sector') and t not in entries:
                entries[t] = {'tier': 'F', 'status': 'financial_na'}
    stats['overrides'] = apply_overrides(entries, mc_o, byt)
    out = {'_definition': 'Net debt = gross interest-bearing debt (excl. IFRS 16 leases) - cash & liquid investments, from the latest published balance sheet (tier A), or the company-reported net debt figure (tier B, definition varies). EV (USD) = current market cap + net debt in USD. Informational only; does not affect the v6 score.',
           '_fx': FX, '_fxNote': FX_NOTE, '_generated': __import__('datetime').date.today().isoformat(), 'entries': entries}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print('stats', stats, '| entries', len(entries))


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--region' in args:
        i = args.index('--region'); REGION = args[i + 1]; del args[i:i + 2]
        OUT = ROOT / CFG[REGION]['dir'] / 'net_debt.json'
    if args[0] == '--overrides-only':
        d = json.load(open(OUT))
        byt = {c['ticker']: c for c in json.load(open(ROOT / CFG[REGION]['dir'] / CFG[REGION]['pool']))}
        k = apply_overrides(d['entries'], json.load(open(ROOT / CFG[REGION]['dir'] / 'mc_overrides_applied.json')), byt)
        OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        print('overrides applied:', k)
    else:
        main(args[0])
