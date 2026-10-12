"""One-time correction: recompute fixedPts['profitability'] (and the
dependent fixedSumNoGm) for every company using the new trend-based,
growth-investment-adjusted measure (scoring.growth_adjusted_profit_pct),
replacing the old sign-only "fraction of periods with NI > 0" measure.

Europe only for now (data/companies_1000_scored.json) - the user asked
to check this batch's impact before applying the same fix to the
US/Canada pool. See docs/handoff-brief.md for the full methodology
discussion (triggered by a question about ProCook Group) and
scripts/scoring.py's growth_adjusted_profit_pct() docstring for the
exact rule.

Usage: python3 scripts/fix_profitability_growth_investment.py
"""
import json
from pathlib import Path

from scoring import growth_adjusted_profit_pct

ROOT = Path(__file__).resolve().parent.parent
POOL_PATH = ROOT / "data" / "companies_1000_scored.json"


def main():
    companies = json.load(open(POOL_PATH))

    changed = []
    for c in companies:
        old_pct = c['profitPct']
        old_pts = c['fixedPts']['profitability']
        new_pct = growth_adjusted_profit_pct(c['niHist'], c['revHist'], c['cfoPct'])
        new_pts = round(new_pct * 16.0, 4)
        if abs(new_pts - old_pts) > 1e-6:
            c['fixedSumNoGm'] = round(c['fixedSumNoGm'] - old_pts + new_pts, 4)
            c['fixedPts']['profitability'] = new_pts
            c['profitPctGrowthAdjusted'] = round(new_pct, 4)
            changed.append((c['ticker'], c['name'], old_pct, round(new_pct, 4), old_pts, new_pts))

    json.dump(companies, open(POOL_PATH, 'w'))

    print(f'{len(changed)} of {len(companies)} companies changed')
    improved = [r for r in changed if r[5] > r[4]]
    worsened = [r for r in changed if r[5] < r[4]]
    print(f'  improved: {len(improved)}, worsened: {len(worsened)}')
    changed.sort(key=lambda r: r[5] - r[4])
    print('\nBiggest decreases (old pct -> new pct, old pts -> new pts):')
    for row in changed[:15]:
        print(f'  {row[0]:16s} {row[1][:30]:30s} {row[2]:.3f} -> {row[3]:.3f}   {row[4]:.2f} -> {row[5]:.2f}')
    print('\nBiggest increases:')
    for row in changed[-15:]:
        print(f'  {row[0]:16s} {row[1][:30]:30s} {row[2]:.3f} -> {row[3]:.3f}   {row[4]:.2f} -> {row[5]:.2f}')

    for c in companies:
        if c['ticker'] == 'LSE:PROC':
            print(f"\nProCook check: old pct {c.get('profitPct')}, "
                  f"new (growth-adjusted) pct {c.get('profitPctGrowthAdjusted', c['profitPct'])}, "
                  f"pts {c['fixedPts']['profitability']}")


if __name__ == '__main__':
    main()
