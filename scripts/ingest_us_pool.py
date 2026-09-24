"""Build data-us/companies_pool.json from the raw USA/Canada Capital IQ
extract (data-us/raw/USA_and_Canada_15m-1B.xls), following the exact v6
methodology documented in data-us/raw/USA_Canada_SmallCap_Value_Shortlist_AllSectors.xlsx's
Methodology sheet - the same model as scripts/scoring.py, applied fresh to
this pool since (unlike Europe) no ingestion script for this universe
existed before this session.

Quality gates (7 steps, all "STRICT" per the methodology):
  1. Remove funds/ETFs/SPACs/trusts/REITs by name pattern.
  2. Track record: >=7 of 10 periods of revenue data.
  3. Positive revenue: every reported period's revenue > 0.
  4. Dilution: <=20% share-count growth over the full period. Unlike the
     original strict exclusion, a company with NO usable share-count data
     is NOT dropped - it gets the pool-median dilution score with
     dilutionDataMissing=True and a visible flag, exactly matching the
     policy the user chose for Europe's 15 no-data companies (2026-09-21).
  5. Positive overall revenue growth (last non-missing / first non-missing - 1 > 0).
  6. Positive latest-annual equity.
  7. Profitability: >=50% of reported periods profitable.

Missing-value convention (confirmed empirically, NOT assumed - see the
'-' vs 0.0 check this session): the literal string '-' marks "not
reported" for every history field. For shares-outstanding specifically,
a literal 0.0 is ALSO a "not reported" placeholder (same trap that
caused the original Europe dilution bug) - 584 such cells were found in
this file. 0.0 is NOT treated as missing for revenue/NI/CFO/dividends,
since e.g. "$0 dividends paid" is a normal, real value for a non-payer.

Usage: python3 scripts/ingest_us_pool.py
"""
import json
import re
from pathlib import Path

import xlrd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data-us" / "raw" / "USA_and_Canada_15m-1B.xls"
OUT = ROOT / "data-us" / "companies_pool_all.json"
OUT_NONFIN = ROOT / "data-us" / "companies_pool_nonfinancial.json"

HEADER_ROW = 7
DATA_START = 8

COL_NAME = 0
COL_TICKER = 1
COL_COUNTRY = 4
COL_MC = 5
COL_EQUITY = 6
NI_COLS = list(range(7, 17))
REV_COLS = list(range(17, 27))
CFO_COLS = list(range(27, 37))
SHARES_COLS = list(range(57, 67))
DIV_COLS = list(range(77, 87))

FUND_PATTERNS = [
    r'\bETF\b', r'Exchange[- ]Traded Fund', r'Index Fund', r'\bSPAC\b',
    r'Acquisition Corp(oration)?\b', r'\bTrust\b', r'\bREIT\b',
    r'Real Estate Investment Trust', r'\bBDC\b',
    r'Business Development Company', r'Closed[- ]End Fund',
    r'\bFund[, ]', r'\bFund$', r'Royalty Trust',
]
FUND_RE = re.compile('|'.join(FUND_PATTERNS), re.IGNORECASE)

FINANCIAL_SECTOR_HINTS = [
    'bank', 'bancorp', 'bancshares', 'savings', 'bankshares', 'financial corp',
    'insurance', 'reinsurance', 'REIT', 'real estate investment trust',
    'asset management', 'capital markets', 'thrift',
]


def is_fund_like(name):
    return bool(FUND_RE.search(name))


def parse_name_ticker(raw_name, ticker):
    """'Company Name, Inc. (NasdaqGS:XYZ)' -> 'Company Name, Inc.'"""
    suffix = f' ({ticker})'
    if raw_name.endswith(suffix):
        return raw_name[:-len(suffix)]
    return re.sub(r'\s*\([^)]*\)\s*$', '', raw_name).strip()


def cell_num(row, col, treat_zero_missing=False):
    v = row[col]
    if isinstance(v, str):
        return None
    if v is None:
        return None
    if treat_zero_missing and v == 0.0:
        return None
    return float(v)


def series(row, cols, treat_zero_missing=False):
    return [cell_num(row, c, treat_zero_missing) for c in cols]


def first_last_nonmissing(vals):
    present = [(i, v) for i, v in enumerate(vals) if v is not None]
    if len(present) < 2:
        return None, None
    return present[0][1], present[-1][1]


def rev_consistency(vals):
    present = [v for v in vals if v is not None]
    if len(present) < 2:
        return 0.0
    increases = sum(1 for a, b in zip(present, present[1:]) if b > a)
    return increases / (len(present) - 1)


def pct_positive(vals):
    present = [v for v in vals if v is not None]
    if not present:
        return 0.0
    return sum(1 for v in present if v > 0) / len(present)


def pct_positive_of_n(vals, n):
    """Dividend consistency: denominator is periods *reported* (n =
    nRevPeriods), since 0.0 is a real 'no dividend' value, not missing."""
    if n == 0:
        return 0.0
    positive = sum(1 for v in vals[-n:] if v is not None and v > 0)
    return positive / n


def load_raw_rows():
    wb = xlrd.open_workbook(str(RAW))
    sh = wb.sheet_by_name('Screening')
    rows = []
    for r in range(DATA_START, sh.nrows):
        row = sh.row_values(r)
        rows.append(row)
    return rows


NON_EQUITY_EXCHANGE_PREFIXES = ('MutualFund:', 'Index:', 'OTCPK:PINK:')


def build_company(row):
    ticker = row[COL_TICKER]
    if not ticker or not isinstance(row[COL_NAME], str):
        return None
    if ticker.startswith(NON_EQUITY_EXCHANGE_PREFIXES):
        return None
    name = parse_name_ticker(row[COL_NAME], ticker)
    if is_fund_like(name):
        return None

    country = row[COL_COUNTRY] if isinstance(row[COL_COUNTRY], str) else None
    mc = cell_num(row, COL_MC)
    equity = cell_num(row, COL_EQUITY)
    ni_hist = series(row, NI_COLS)
    rev_hist = series(row, REV_COLS)
    cfo_hist = series(row, CFO_COLS)
    shares_hist = series(row, SHARES_COLS, treat_zero_missing=True)
    div_hist = series(row, DIV_COLS)

    n_rev_periods = sum(1 for v in rev_hist if v is not None)
    if n_rev_periods < 7:
        return None
    reported_rev = [v for v in rev_hist if v is not None]
    if any(v <= 0 for v in reported_rev):
        return None

    rev_first, rev_last = first_last_nonmissing(rev_hist)
    if rev_first is None or rev_first <= 0:
        return None
    rev_growth = (rev_last / rev_first) - 1
    if rev_growth <= 0:
        return None

    if equity is None or equity <= 0:
        return None

    profit_pct = pct_positive(ni_hist)
    if profit_pct < 0.5:
        return None

    dil_first, dil_last = first_last_nonmissing(shares_hist)
    dilution = None
    dilution_missing = True
    if dil_first is not None and dil_first > 0:
        dilution = (dil_last / dil_first) - 1
        dilution_missing = False
        if dilution > 0.20:
            return None

    avg_ni = None
    recent = [v for v in ni_hist[-4:] if v is not None]
    if recent:
        avg_ni = sum(recent) / len(recent)

    return {
        'ticker': ticker, 'name': name, 'country': country,
        'mc0': mc, 'equity': equity,
        'revLTM': rev_last, 'revGrowth': rev_growth,
        'dilution': dilution, 'dilutionDataMissing': dilution_missing,
        'avgNI': avg_ni,
        'profitPct': profit_pct,
        'cfoPct': pct_positive(cfo_hist),
        'divPct': pct_positive_of_n(div_hist, n_rev_periods),
        'nRevPeriods': n_rev_periods,
        'revConsistency': rev_consistency(rev_hist),
        'revHist': rev_hist, 'niHist': ni_hist,
        'is_financial_sector': any(h in name.lower() for h in FINANCIAL_SECTOR_HINTS),
    }


def main():
    rows = load_raw_rows()
    companies = []
    for row in rows:
        c = build_company(row)
        if c:
            companies.append(c)

    print(f'{len(rows)} raw rows -> {len(companies)} survivors after quality gates')

    seen = set()
    deduped = []
    for c in companies:
        if c['ticker'] in seen:
            continue
        seen.add(c['ticker'])
        deduped.append(c)
    companies = deduped
    print(f'{len(companies)} after de-dup by ticker')

    nonfin = [c for c in companies if not c['is_financial_sector']]
    print(f'{len(nonfin)} non-financial survivors')

    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(companies, f)
    with open(OUT_NONFIN, 'w') as f:
        json.dump(nonfin, f)
    print(f'saved -> {OUT} and {OUT_NONFIN}')


if __name__ == '__main__':
    main()
