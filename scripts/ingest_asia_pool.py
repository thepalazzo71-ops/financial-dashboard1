"""Build the Asia/Pacific pool from the raw Capital IQ extract
(data-asia/raw/Asia_15m-1B.xls, "Asia / Pacific Developed Markets",
US$15M-1B market cap, same 87-column layout as the Europe/US extracts).

Same v6 methodology and the same seven quality gates as the Europe and
USA/Canada pools - scripts/ingest_us_pool.py's build_company() is reused
unchanged (including the 2026-10-26 IPO-stub dilution rule in
scripts/dilution_rule.py) and scripts/us_scoring.compute_fixed_pts() gives
the fixed-dimension points. Like USA/Canada, ALL gate survivors form the
pool (no top-N cut): a gross margin is unknown at first (pool-median
fallback) and research proceeds in tiers by current rank.

Two pools are written, as for USA/Canada: companies_pool_all.json and
companies_pool_nonfinancial.json (banks/insurers/brokers/leasing... have no
gross-profit line, so the non-financial pool is the one where gross margin
research is meaningful). The financial flag is a name heuristic.

Usage: python3 scripts/ingest_asia_pool.py   (idempotent; REPLACES the pool
files - run it only for the initial build, later updates are merged by
scripts/apply_*.py style scripts).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ingest_us_pool as I
import us_scoring as U
from dilution_rule import measure_dilution

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data-asia" / "raw" / "Asia_15m-1B.xls"
OUT_ALL = ROOT / "data-asia" / "companies_pool_all.json"
OUT_NONFIN = ROOT / "data-asia" / "companies_pool_nonfinancial.json"

# Name hints (case-insensitive) for companies with no gross-profit line.
FINANCIAL_HINTS = [
    'bank', 'bancorp', 'bancshares', 'savings', 'financial', 'finance', 'insurance', 'assurance',
    'reinsurance', 'securities', 'asset management', 'capital markets', 'thrift', 'leasing',
    'credit', 'shinkin', 'mutual', 'lending', 'brokerage',
]
NOT_FINANCIAL = ['soft bank', 'softbank', 'banks yachts', 'life science', 'gemdale']


# Offshore-incorporated companies (Cayman/Bermuda/BVI/...) are shown under the
# country of their primary listing, which says where the business is; the
# incorporation is kept in the `incorporation` field.
OFFSHORE = {'Cayman Islands', 'Bermuda', 'British Virgin Islands', 'Jersey', 'Guernsey', 'Luxembourg', 'Netherlands', 'Denmark', 'Ireland'}
LISTING_COUNTRY = {
    'SEHK': 'Hong Kong', 'TSE': 'Japan', 'KOSDAQ': 'South Korea', 'KOSE': 'South Korea', 'SGX': 'Singapore',
    'Catalist': 'Singapore', 'ASX': 'Australia', 'NZSE': 'New Zealand', 'NSE': 'India', 'SPSE': 'Japan',
    'FKSE': 'Japan', 'XKON': 'South Korea',
}


def is_financial(name):
    n = ' ' + name.lower() + ' '
    return any(h in n for h in FINANCIAL_HINTS) and not any(x in n for x in NOT_FINANCIAL)


def main():
    I.RAW = RAW
    rows = I.load_raw_rows()
    seen, pool = set(), []
    for r in rows:
        c = I.build_company(r)
        if not c or c['ticker'] in seen:
            continue
        seen.add(c['ticker'])
        if measure_dilution(I.series(r, I.SHARES_COLS, treat_zero_missing=True))[1]:
            c['dilutionAdjusted'] = True  # measured after an IPO/restatement stub (see dilution_rule.py)
        c['incorporation'] = c['country']
        listing = LISTING_COUNTRY.get(c['ticker'].split(':')[0])
        if listing and (c['country'] in OFFSHORE or not c['country']):
            c['country'] = listing
        c['is_financial_sector'] = is_financial(c['name'])
        c['gm'] = None
        c['gmIsVerified'] = False
        c['hasThesis'] = False
        c['thesis'] = None
        c['industry'] = None
        c['archetype'] = None
        c['fixedPts'], c['fixedSumNoGm'] = U.compute_fixed_pts(c)
        pool.append(c)
    nonfin = [c for c in pool if not c['is_financial_sector']]
    OUT_ALL.parent.mkdir(exist_ok=True)
    json.dump(pool, open(OUT_ALL, 'w'))
    json.dump(nonfin, open(OUT_NONFIN, 'w'))
    print(f'{len(rows)} raw rows -> {len(pool)} survivors ({len(nonfin)} non-financial); wrote {OUT_ALL.name}, {OUT_NONFIN.name}')


if __name__ == '__main__':
    main()
