"""One-time correction: apply the gross-margin + long-term-revenue-growth
+ CFO-positive profitability bonus (scoring.apply_profitability_bonus) to
every company in both pools, replacing fixedPts['profitability'] and the
dependent fixedSumNoGm wherever it qualifies.

Previewed client-side first (both dashboards' "Profitability bonus
preview" modal) before running this for real - see
docs/handoff-brief.md for the full methodology discussion (triggered by
a question about ProCook Group) and the rejected alternatives tried
before landing on this rule.

Usage: python3 scripts/apply_profitability_bonus.py
"""
import json
from pathlib import Path

from scoring import apply_profitability_bonus, full_history_cagr

ROOT = Path(__file__).resolve().parent.parent


def correct_file(path, label):
    companies = json.load(open(path))
    changed = []
    for c in companies:
        old_pts = c['fixedPts']['profitability']
        new_pts = apply_profitability_bonus(old_pts, c.get('gm'), c.get('cfoPct'), c['revHist'])
        if new_pts != old_pts:
            c['fixedSumNoGm'] = round(c['fixedSumNoGm'] - old_pts + new_pts, 4)
            c['fixedPts']['profitability'] = new_pts
            c['profitabilityBonusApplied'] = True
            changed.append((c['ticker'], c['name'], old_pts, new_pts))
    json.dump(companies, open(path, 'w'))
    print(f'{label}: {len(changed)} of {len(companies)} companies bonused')
    for t, n, op, np_ in sorted(changed, key=lambda r: -(r[3]-r[2]))[:10]:
        print(f'  {t:16s} {n[:30]:30s} {op:.2f} -> {np_:.2f}')
    return changed


def main():
    correct_file(ROOT / 'data' / 'companies_1000_scored.json', 'Europe')
    correct_file(ROOT / 'data-us' / 'companies_pool_all.json', 'US all-sector')
    correct_file(ROOT / 'data-us' / 'companies_pool_nonfinancial.json', 'US non-financial')

    d = json.load(open(ROOT / 'data' / 'companies_1000_scored.json'))
    proc = next(c for c in d if c['ticker'] == 'LSE:PROC')
    print(f"\nProCook check: profitability pts = {proc['fixedPts']['profitability']}, "
          f"fixedSumNoGm = {proc['fixedSumNoGm']}, bonusApplied = {proc.get('profitabilityBonusApplied')}")


if __name__ == '__main__':
    main()
