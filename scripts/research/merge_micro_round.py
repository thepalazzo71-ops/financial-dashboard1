"""Merge a Europe-micro market-cap / listing-status / corporate-actions research round (docs/research-prompts/micro_mc_instructions.md)
into data-micro/: mc_overrides_applied.json (local market cap converted to USD at approximate FX), corporate_actions.json,
corporate_actions_coverage.json, distress_flags.json (insolvency) and delisted.json (completed delistings).
Usage: python3 scripts/merge_micro_round.py <out.json> [<out.json> ...]   (files are {ticker: {listing_status, listing_notes, mc, corp_actions, notes}})
"""
import json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / 'data-micro'
# USD per unit of currency; APPROXIMATE (ECB reference rates May-July 2026, as in scripts/merge_net_debt.py)
EURUSD = 1.1383
FX = {'EUR': EURUSD, 'GBP': round(EURUSD / 0.85973, 4), 'SEK': round(EURUSD / 11.036, 5), 'NOK': round(EURUSD / 11.077, 5),
      'CHF': round(EURUSD / 0.9257, 4), 'PLN': round(EURUSD / 4.3383, 5), 'DKK': round(EURUSD / 7.4745, 5),
      'RON': round(EURUSD / 5.1977, 5), 'BGN': round(EURUSD / 1.95583, 5), 'USD': 1.0}


def load(name, default):
    p = D / name
    return json.load(open(p)) if p.exists() else default


def main(files):
    res = {}
    for f in files:
        res.update(json.load(open(f)))
    names = {c['ticker']: c['name'] for c in load('companies_pool_all.json', [])}
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    mc = load('mc_overrides_applied.json', {})
    ca = load('corporate_actions.json', {'tender_offers': [], 'mergers_acquisitions': [], 'spinoffs': [], 'other': []})
    cov = load('corporate_actions_coverage.json', {'screened': [], 'total_priority_pool': 0})
    dist = load('distress_flags.json', {'_definition': 'Curated list of Europe-micro companies in current financial distress / insolvency proceedings (same definition as the Europe file). Informational only.'})
    dl = load('delisted.json', {'_definition': 'Companies whose stock is no longer tradable because a takeover, squeeze-out, share exchange or delisting has COMPLETED. Same convention as data/delisted.json (Europe).'})
    n_mc = n_ca = 0
    for t, v in res.items():
        m = v.get('mc') or {}
        cur, loc = m.get('currency'), m.get('market_cap_local_mm')
        if loc is not None and cur in FX and v.get('listing_status') != 'delisted':
            mc[t] = {'mc': round(float(loc) * FX[cur], 3), 'source': m.get('source_url'), 'updatedAt': now,
                     'quoteDate': m.get('date'), 'local': f"{cur} {loc}m", 'fx': FX[cur]}
            n_mc += 1
        for a in v.get('corp_actions') or []:
            a = dict(a); cat = a.pop('category', 'other')
            if cat not in ca:
                cat = 'other'
            e = {'ticker': t, 'company': names.get(t, t)}; e.update(a)
            if not any(x.get('ticker') == t and x.get('source_url') == e.get('source_url') and x.get('date') == e.get('date') for x in ca[cat]):
                ca[cat].append(e); n_ca += 1
        st = v.get('listing_status')
        if st == 'insolvency':
            dist[t] = {'level': 'severe', 'summary': (v.get('listing_notes') or '')[:600], 'asOf': now[:10],
                       'sources': [m.get('source_url')] if m.get('source_url') else []}
        elif st == 'delisted':
            dl[t] = {'date': now[:10], 'price': '', 'reason': (v.get('listing_notes') or '')[:500], 'sources': []}
        if t not in cov['screened']:
            cov['screened'].append(t)
    cov['total_priority_pool'] = len(names)
    json.dump(mc, open(D / 'mc_overrides_applied.json', 'w'), separators=(',', ':'))
    json.dump(ca, open(D / 'corporate_actions.json', 'w'), indent=1, ensure_ascii=False)
    json.dump(cov, open(D / 'corporate_actions_coverage.json', 'w'), indent=1)
    json.dump(dist, open(D / 'distress_flags.json', 'w'), indent=1, ensure_ascii=False)
    json.dump(dl, open(D / 'delisted.json', 'w'), indent=1, ensure_ascii=False)
    print(f'market caps {n_mc}, corporate actions {n_ca}, screened {len(cov["screened"])}')
    for t, v in res.items():
        if not (v.get('mc') or {}).get('market_cap_local_mm'):
            print('no market cap:', t)


if __name__ == '__main__':
    main(sys.argv[1:])
