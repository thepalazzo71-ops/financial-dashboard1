"""Industry-peer gross-margin ESTIMATES for the Asia/Pacific pool (re-runnable).

Where no gross margin could be found for a non-financial company (the search
passes in data-asia/gm_research_log.json), the pool used to fall back to the
pool-median gross-margin *points* with no gross margin at all (so the
GM-adjusted P/S lens was missing too). This script instead assigns the median
gross margin of the company's industry peers that DO have a sourced margin:

  - data-asia/gm_industry.json maps ticker -> {industry_group, confidence, business?}
    (classified by research agents from name / business description);
  - peers = companies in the same industry_group with a sourced margin
    (gm set and gmEstimated falsy); groups with fewer than MIN_PEERS peers use
    the whole-sample median;
  - the estimate is written as gm + gmEstimated=True, gmEstGroup, gmEstPeers,
    gmSourceType='industry_estimate', gmIsVerified=False.
  - fixedPts is recomputed with gm=None for estimated companies, so the
    high-gross-margin profitability bonus is never granted on an estimate.

Back-test (leave-one-out over the 948 sourced margins, 2026-10-29): the group
median misses by 11.3 gross-margin points on average vs 13.2 for the global
median - a modest gain, so estimates are shown as "est. GM", never as verified.
Delisted companies and companies with no gross-profit line (financial-like) are
skipped. Usage: python3 scripts/apply_gm_estimates.py [--clear]
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import us_scoring as U

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data-asia"
MIN_PEERS = 10


def main():
    clear = '--clear' in sys.argv
    industry = json.load(open(D / 'gm_industry.json'))
    log = json.load(open(D / 'gm_research_log.json'))['results']
    delisted = set(json.load(open(D / 'delisted.json')))
    for name in ('companies_pool_all.json', 'companies_pool_nonfinancial.json'):
        path = D / name
        pool = json.load(open(path))
        # drop previous estimates first (idempotent)
        for c in pool:
            if c.get('gmEstimated'):
                for k in ('gm', 'gmEstimated', 'gmEstGroup', 'gmEstPeers', 'gmSourceType', 'gmFiscalYear', 'gmSourceUrl'):
                    c.pop(k, None) if k != 'gm' else None
                c['gm'] = None
                c['gmIsVerified'] = False
                c['fixedPts'], c['fixedSumNoGm'] = U.compute_fixed_pts(c)
        sourced = {}
        for c in pool:
            if c.get('gm') is not None and industry.get(c['ticker']):
                sourced.setdefault(industry[c['ticker']]['industry_group'], []).append(c['gm'])
        everyone = [x for v in sourced.values() for x in v]
        n_est = 0
        if not clear:
            for c in pool:
                t = c['ticker']
                if c.get('gm') is not None or c.get('is_financial_sector') or t in delisted:
                    continue
                if (log.get(t) or {}).get('status') == 'no_gross_profit_line':
                    continue
                g = (industry.get(t) or {}).get('industry_group')
                if not g:
                    continue
                peers = sourced.get(g, [])
                use = peers if len(peers) >= MIN_PEERS else everyone
                c['gm'] = round(statistics.median(use), 4)
                c['gmEstimated'] = True
                c['gmEstGroup'] = g if len(peers) >= MIN_PEERS else 'all (too few peers in group)'
                c['gmEstPeers'] = len(use)
                c['gmSourceType'] = 'industry_estimate'
                c['gmIsVerified'] = False
                c['fixedPts'], c['fixedSumNoGm'] = U.compute_fixed_pts(dict(c, gm=None))
                n_est += 1
        json.dump(pool, open(path, 'w'))
        print(f'{name}: {n_est} estimates applied, {len(everyone)} sourced peers')


if __name__ == '__main__':
    main()
