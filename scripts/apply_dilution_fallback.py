"""One-off (re-runnable) fix: companies with dilution=null currently score
0/12 on the dilution dimension (worst-case), even though the underlying
share-count data is genuinely unavailable anywhere in the raw Capital IQ
extract (not a parsing gap - see fix_dilution_gaps.py for the 69 that
were fixable; these 15 are not). Zero-as-worst-case is inconsistent with
how missing gross margin is handled (pool median fallback) and penalizes
these companies for a data gap, not a real finding.

Per the user's decision (2026-09-21): use the pool's median dilution_pts
as a neutral fallback (same pattern as gross margin), and mark the
company with `dilutionDataMissing: true` so the dashboard can flag it
visibly rather than silently blending it in - the user explicitly wants
this visible, not hidden.

Usage: python3 scripts/apply_dilution_fallback.py
"""
import json
import statistics

from scoring import DATA, load_companies

POOL_PATH = DATA / "companies_1000_scored.json"


def main():
    companies = load_companies()

    with_data = [c['fixedPts']['dilution'] for c in companies if c.get('dilution') is not None]
    median_pts = statistics.median(with_data)

    fixed = 0
    for c in companies:
        if c.get('dilution') is not None:
            c['dilutionDataMissing'] = False
            continue
        old_pts = c['fixedPts']['dilution']
        c['fixedPts']['dilution'] = round(median_pts, 4)
        c['fixedSumNoGm'] = round(c['fixedSumNoGm'] - old_pts + median_pts, 4)
        c['dilutionDataMissing'] = True
        fixed += 1

    with open(POOL_PATH, 'w') as f:
        json.dump(companies, f)
    print(f'applied median dilution fallback ({median_pts:.2f}/12) to {fixed} companies '
          f'with no usable share-count data; run scripts/build_site.py next to resync ranks')


if __name__ == '__main__':
    main()
