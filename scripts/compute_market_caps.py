#!/usr/bin/env python3
"""Market cap = share count x last close, replacing ESTIMATED market caps.

  python3 scripts/compute_market_caps.py --region asia [--also-researched-older-than DAYS] [--dry-run]

Share count: `sharesMm` stored by scripts/fetch_yahoo_net_debt.py in <folder>/net_debt.json (Yahoo fundamentals
feed, OrdinarySharesNumber on the latest balance-sheet date).  Price: last close from data-prices/price_stats.json in
the TRADING currency (GBp -> GBP / 100), converted to USD at today's Yahoo FX.

What it replaces in <folder>/mc_overrides_applied.json:
  * entries tagged `derived` (price-move estimates)             -> always (unless the sanity check fails)
  * researched/quoted entries                                     -> only with --also-researched-older-than and when
                                                                     their quote is older than that many days
  * companies without any entry                                   -> added
Sanity check: the new value must be within 0.4x-2.5x of the current figure (extract value if none); bigger gaps usually
mean a share-class or ADR mismatch and are printed, not applied.  New entries are tagged `computed`.
"""
import argparse, json, sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import derive_market_caps as D
import price_stats as PS

ROOT = Path(__file__).resolve().parent.parent
FOLDERS = {'asia': 'data-asia', 'eu': 'data', 'us': 'data-us', 'micro': 'data-micro'}
LO, HI = 0.4, 2.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--region', required=True, choices=list(FOLDERS))
    ap.add_argument('--also-researched-older-than', type=int)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    folder = ROOT / FOLDERS[a.region]
    pool_file = folder / ('companies_1000_scored.json' if a.region == 'eu' else 'companies_pool_all.json')
    pool = {c['ticker']: c for c in json.load(open(pool_file))}
    ov_path = folder / 'mc_overrides_applied.json'
    ov = json.load(open(ov_path))
    nd = json.load(open(folder / 'net_debt.json')).get('entries', {})
    stats = PS._load()
    ref = PS.as_of()
    today = date.today()
    fx = {}

    def rate(cur):
        base = 'GBP' if cur == 'GBp' else cur
        if base == 'USD':
            r = 1.0
        else:
            if base not in fx:
                s, _ = D.series(base + 'USD=X')
                fx[base] = s[max(s)] if s else None
            r = fx[base]
        return None if r is None else (r / 100 if cur == 'GBp' else r)

    applied, skipped, outliers, ratios = 0, {}, [], []
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    for t, c in pool.items():
        e = nd.get(t) or {}
        sh = e.get('sharesMm')
        px = PS.px_for(t)
        if not sh or not px:
            skipped['no shares or price'] = skipped.get('no shares or price', 0) + 1
            continue
        r = rate(px['cur'])
        if r is None:
            skipped['no FX'] = skipped.get('no FX', 0) + 1
            continue
        new = sh * px['l'] * r
        cur = ov.get(t)
        if cur and not cur.get('derived') and not cur.get('computed'):
            qd = cur.get('quoteDate') or (cur.get('updatedAt') or '')[:10]
            try:
                age = (today - date.fromisoformat(str(qd)[:10])).days
            except Exception:
                age = 9999
            if a.also_researched_older_than is None or age <= a.also_researched_older_than:
                ratios.append(new / cur['mc'])            # keep researched: only used to validate
                skipped['kept researched quote'] = skipped.get('kept researched quote', 0) + 1
                continue
        base = cur['mc'] if cur else c.get('mc0')
        q = new / base if base else None
        if q is None or not (LO <= q <= HI):
            outliers.append((t, c['name'][:28], round(base or 0, 1), round(new, 1), None if q is None else round(q, 2), px['s'] if 's' in px else '', sh))
            continue
        ov[t] = {'mc': round(new, 3), 'computed': True, 'updatedAt': now, 'quoteDate': px['d'],
                 'source': f"computed: {sh:g}m shares (Yahoo balance sheet {e.get('balanceSheetDate')}) x last close {px['l']:g} {px['cur']} ({px['d']})",
                 'shares': sh, 'price': px['l'], 'cur': px['cur'], 'fx': r}
        applied += 1
    print(f'{a.region}: applied {applied} | skipped {skipped} | outliers (not applied) {len(outliers)}')
    if ratios:
        ratios.sort()
        within = sum(1 for x in ratios if 0.85 <= x <= 1.15)
        print(f'validation vs researched quotes: {len(ratios)} compared, median ratio {ratios[len(ratios)//2]:.3f}, {within} within +/-15%')
    for o in outliers[:25]:
        print('   outlier', o)
    if not a.dry_run:
        json.dump(ov, open(ov_path, 'w'))
        print('wrote', ov_path)


if __name__ == '__main__':
    main()
