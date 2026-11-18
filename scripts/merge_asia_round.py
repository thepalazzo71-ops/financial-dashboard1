#!/usr/bin/env python3
"""Merge an Asia corporate-actions / listing-status / quoted-market-cap research round
(docs/research-prompts/asia_ca_instructions.md) into data-asia/.

  python3 scripts/merge_asia_round.py <out.json> [<out.json> ...] [--max-quote-age 75] [--dry-run]

Each out file is {ticker: {listing_status, listing_notes, mc:{market_cap_local_mm, currency, price, shares_mm, date,
source_url, notes}, corp_actions:[...], notes}}.

 * corporate actions -> data-asia/corporate_actions.json (deduplicated), coverage -> corporate_actions_coverage.json
 * 'insolvency' -> distress_flags.json (severe), 'suspended' -> distress_flags.json (warning),
   'delisted' -> delisted.json (completed delistings are hidden from the ranking and listed in the Delisted window)
 * market cap: converted to USD at today's Yahoo FX (<CUR>USD=X).  A researched quote REPLACES an existing
   price-derived estimate only when it is recent (--max-quote-age days, default 75), because the derived figure
   uses today's price; an older quote is kept in the log but not applied.  The ratio researched/derived is printed:
   large gaps usually mean the share count changed since March (rights issue, buyback), which is exactly what the
   derived method cannot see.
"""
import argparse, json, sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import derive_market_caps as D

ROOT = Path(__file__).resolve().parent.parent
F = ROOT / 'data-asia'


def load(name, default):
    p = F / name
    return json.load(open(p)) if p.exists() else default


def save(name, obj, compact=False):
    with open(F / name, 'w') as f:
        json.dump(obj, f, ensure_ascii=False, **({} if compact else {'indent': 1}))


def fx_now(cur, cache):
    if cur == 'USD':
        return 1.0
    if cur not in cache:
        s, _ = D.series(cur + 'USD=X')
        cache[cur] = s[max(s)] if s else None
    return cache[cur]


def parse_date(s):
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+')
    ap.add_argument('--max-quote-age', type=int, default=75)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    res = {}
    for f in a.files:
        res.update(json.load(open(f)))
    pool = {c['ticker']: c for c in load('companies_pool_all.json', [])}
    now = datetime.now(timezone.utc)
    today = now.date()
    mc = load('mc_overrides_applied.json', {})
    ca = load('corporate_actions.json', {'tender_offers': [], 'mergers_acquisitions': [], 'spinoffs': [], 'other': []})
    cov = load('corporate_actions_coverage.json', {'screened': [], 'total_priority_pool': len(pool)})
    dist = load('distress_flags.json', {})
    dl = load('delisted.json', {})
    fx, n_mc, n_old, n_ca, gaps = {}, 0, 0, 0, []
    status_counts = {}
    for t, v in res.items():
        if t not in pool:
            print('unknown ticker', t)
            continue
        name = pool[t]['name']
        st = v.get('listing_status') or 'unknown'
        status_counts[st] = status_counts.get(st, 0) + 1
        m = v.get('mc') or {}
        loc, cur = m.get('market_cap_local_mm'), m.get('currency')
        if loc is not None and cur and st != 'delisted':
            rate = fx_now(cur, fx)
            qd = parse_date(m.get('date'))
            if rate is None:
                print('no FX for', cur, t)
            else:
                usd = float(loc) * rate
                cur_est = mc.get(t, {}).get('mc') or pool[t]['mc0']
                ratio = usd / cur_est if cur_est else None
                fresh = qd is not None and (today - qd).days <= a.max_quote_age
                existing_researched = t in mc and not mc[t].get('derived')
                if fresh and not existing_researched:
                    mc[t] = {'mc': round(usd, 3), 'source': m.get('source_url'), 'updatedAt': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
                             'quoteDate': str(qd), 'local': f'{cur} {loc}m', 'fx': round(rate, 8)}
                    n_mc += 1
                else:
                    n_old += 1
                if ratio and (ratio > 1.4 or ratio < 0.7):
                    gaps.append((t, name[:28], round(ratio, 2), str(qd), 'APPLIED' if fresh and not existing_researched else 'kept old/derived'))
        for x in v.get('corp_actions') or []:
            x = dict(x)
            cat = x.pop('category', 'other')
            if cat not in ca:
                cat = 'other'
            e = {'ticker': t, 'company': name}
            e.update(x)
            if not any(y.get('ticker') == t and y.get('source_url') == e.get('source_url') and y.get('date') == e.get('date') for y in ca[cat]):
                ca[cat].append(e)
                n_ca += 1
        notes = (v.get('listing_notes') or '')[:600]
        srcs = [m.get('source_url')] if m.get('source_url') else []
        if st == 'insolvency':
            dist[t] = {'level': 'severe', 'summary': notes, 'asOf': str(today), 'sources': srcs}
        elif st == 'suspended':
            dist[t] = {'level': 'warning', 'summary': 'Trading suspended: ' + notes[:560], 'asOf': str(today), 'sources': srcs}
        elif st == 'delisted':
            dl[t] = {'date': str(today), 'price': '', 'reason': notes[:500], 'sources': srcs}
        if t not in cov['screened']:
            cov['screened'].append(t)
    cov['total_priority_pool'] = len(pool)
    print('statuses:', status_counts)
    print(f'market caps applied {n_mc} (researched quote newer than {a.max_quote_age}d), kept derived/older {n_old}; corporate actions added {n_ca}; screened total {len(cov["screened"])}')
    if gaps:
        print('researched vs current estimate differs by >40% / <-30% (check share-count changes):')
        for g in sorted(gaps, key=lambda g: g[2]):
            print('  ', g)
    if a.dry_run:
        return
    save('mc_overrides_applied.json', mc, compact=True)
    save('corporate_actions.json', ca)
    save('corporate_actions_coverage.json', cov)
    save('distress_flags.json', dist)
    save('delisted.json', dl)


if __name__ == '__main__':
    main()
