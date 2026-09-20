"""Regenerate the dashboard snapshot .xlsx from the scored pool + applied overrides.

Run before every write to the dashboard's `overrides` db collection, per the
market-cap refresh workflow (see docs/handoff-brief.md). Reads:
  - data/companies_1000_scored.json  (the 1000-company scored pool, v6 model)
  - data/mc_overrides_applied.json   (ticker -> current market cap in $M,
    mirrors the dashboard's `overrides` collection)

Writes a dated snapshot to snapshots/shortlist_snapshot_<date>.xlsx.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SNAPSHOTS = ROOT / "snapshots"

companies = json.load(open(DATA / "companies_1000_scored.json"))
mc_overrides = json.load(open(DATA / "mc_overrides_applied.json"))


def gm_band_points(gm):
    if gm is None:
        return None
    if gm >= 0.60:
        return 18.0
    if gm >= 0.50:
        return 15.3
    if gm >= 0.40:
        return 12.6
    if gm >= 0.30:
        return 9.9
    if gm >= 0.20:
        return 7.2
    if gm >= 0.10:
        return 4.5
    if gm >= 0.05:
        return 1.8
    return 0.0


def lenses(c, mc):
    A = B = C = None
    if c['gm'] is not None and c['gm'] > 0 and c['revLTM']:
        A = (mc / c['revLTM']) / c['gm']
    roe = (c['avgNI'] / c['equity']) if (c['avgNI'] is not None and c['equity']) else None
    if c['equity'] and c['equity'] > 0 and roe is not None:
        B = (mc / c['equity']) / max(roe / 0.10, 0.1)
    if c['avgNI'] is not None and mc:
        g = min(max(c['revGrowth'] or 0, 0), 2.0)
        C = (c['avgNI'] / mc) * (1 + g)
    return A, B, C, roe


def percentile_rank(values, idx, higher_better):
    v = values[idx]
    if v is None:
        return None
    others = [x for x in values if x is not None]
    n = len(others)
    if n <= 1:
        return 100.0
    beat = sum(1 for x in others if (x < v if higher_better else x > v))
    return 100.0 * beat / (n - 1)


def build_rows():
    gm_pts_all = sorted(gm_band_points(c['gm']) for c in companies if c['gm'] is not None)
    n = len(gm_pts_all)
    median_gm_pts = gm_pts_all[n // 2] if n % 2 else (gm_pts_all[n // 2 - 1] + gm_pts_all[n // 2]) / 2

    mcs = [mc_overrides.get(c['ticker'], c['mc0']) for c in companies]
    A_list, B_list, C_list, ROE_list = [], [], [], []
    for c, mc in zip(companies, mcs):
        a, b, cc, roe = lenses(c, mc)
        A_list.append(a)
        B_list.append(b)
        C_list.append(cc)
        ROE_list.append(roe)

    rows = []
    for i, c in enumerate(companies):
        pA = percentile_rank(A_list, i, False)
        pB = percentile_rank(B_list, i, False)
        pC = percentile_rank(C_list, i, True)
        best = max([p for p in [pA, pB, pC] if p is not None], default=0)
        val_pts = best / 100 * 18
        gm_pts = gm_band_points(c['gm']) if c['gm'] is not None else median_gm_pts
        total = round(c['fixedSumNoGm'] + gm_pts + val_pts, 2)
        pb = mcs[i] / c['equity'] if c['equity'] else None
        rows.append({
            'ticker': c['ticker'], 'name': c['name'], 'country': c['country'],
            'mc': round(mcs[i], 2), 'mc_is_updated': c['ticker'] in mc_overrides,
            'equity': c['equity'], 'pb': round(pb, 3) if pb else None,
            'roe': round(ROE_list[i], 4) if ROE_list[i] is not None else None,
            'rev_growth': round(c['revGrowth'], 4) if c['revGrowth'] is not None else None,
            'gm': c['gm'], 'gm_is_fallback': c['gm'] is None,
            'gm_fiscal_year': c['gmFiscalYear'], 'gm_source_type': c['gmSourceType'],
            'rev_growth_pts': c['fixedPts']['revenue_growth'],
            'rev_consistency_pts': c['fixedPts']['revenue_consistency'],
            'dilution_pts': c['fixedPts']['dilution'],
            'valuation_pts': round(val_pts, 2),
            'profitability_pts': c['fixedPts']['profitability'],
            'cfo_pts': c['fixedPts']['cfo_positive'],
            'track_record_pts': c['fixedPts']['track_record'],
            'dividend_pts': c['fixedPts']['dividend_consistency'],
            'gm_pts': round(gm_pts, 2),
            'total_score': total,
        })

    rows.sort(key=lambda r: -r['total_score'])
    for i, r in enumerate(rows):
        r['rank'] = i + 1
    return rows


def write_workbook(rows, out_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Snapshot'

    snap_dt = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    ws['A1'] = 'European Small/Mid-Cap Value Shortlist — Dashboard Snapshot'
    ws['A1'].font = Font(name='Arial', size=14, bold=True)
    ws['A2'] = f'Captured {snap_dt}, before batch market-cap/GM update'
    ws['A2'].font = Font(name='Arial', size=10, italic=True, color='555555')
    ws['A3'] = f'{len(rows)} companies in candidate pool (percentile-ranked against full pool)'
    ws['A3'].font = Font(name='Arial', size=10, color='555555')

    headers = ['Rank', 'Ticker', 'Company', 'Country', 'Mkt Cap ($M)', 'MC updated?',
               'P/B', 'ROE', 'Rev Growth', 'Gross Margin', 'GM fallback?', 'GM FY', 'GM Source',
               'RevGrowth pts', 'RevConsist pts', 'Dilution pts', 'Valuation pts',
               'Profitability pts', 'CFO+ pts', 'TrackRecord pts', 'Dividend pts', 'GM pts',
               'v6 Total Score']
    header_row = 5
    for j, h in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=j, value=h)
        cell.font = Font(name='Arial', size=10, bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='2F4B3C')
        cell.alignment = Alignment(horizontal='center')

    field_order = ['rank', 'ticker', 'name', 'country', 'mc', 'mc_is_updated', 'pb', 'roe', 'rev_growth',
                   'gm', 'gm_is_fallback', 'gm_fiscal_year', 'gm_source_type',
                   'rev_growth_pts', 'rev_consistency_pts', 'dilution_pts', 'valuation_pts',
                   'profitability_pts', 'cfo_pts', 'track_record_pts', 'dividend_pts', 'gm_pts', 'total_score']
    for i, r in enumerate(rows, start=header_row + 1):
        for j, f in enumerate(field_order, start=1):
            ws.cell(row=i, column=j, value=r[f])

    widths = [6, 14, 32, 16, 12, 11, 7, 8, 10, 11, 11, 7, 16, 12, 12, 11, 12, 14, 9, 13, 11, 7, 12]
    for j, w in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + j) if j <= 26 else 'A' + chr(64 + j - 26)].width = w

    ws.freeze_panes = f'A{header_row + 1}'
    wb.save(out_path)


if __name__ == '__main__':
    rows = build_rows()
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime('%Y-%m-%d')
    SNAPSHOTS.mkdir(exist_ok=True)
    out_path = SNAPSHOTS / f'shortlist_snapshot_{date_str}.xlsx'
    write_workbook(rows, out_path)
    print(f'saved {len(rows)} rows -> {out_path}')
