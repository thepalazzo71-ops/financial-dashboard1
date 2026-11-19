"""Adds `divHist` (dividends paid per trailing-12-month period, $USDm, positive = cash paid out, 0 = none paid,
None = not reported) to every pool file, read from the Capital IQ screening extracts' "Total Dividends Paid [LTM-36 ... LTM]"
columns (cols 77-86, same 10 periods as niHist/revHist).  Capital IQ reports payments as negative numbers; '-' = not reported.

Also prints a check of the derived paid-periods share against each company's stored divPct.
Idempotent.  Usage: python3 scripts/add_div_hist.py
"""
import json
from pathlib import Path

import xlrd

ROOT = Path(__file__).resolve().parent.parent
DIV_COLS = list(range(77, 87))
REGIONS = {
    'data': (['data/raw/Europe_15m-1B.xls'], ['companies_1000_scored.json', 'companies_pool_all.json', 'companies_pool_nonfinancial.json']),
    'data-us': (['data-us/raw/USA_and_Canada_15m-1B.xls'], ['companies_pool_all.json', 'companies_pool_nonfinancial.json']),
    'data-asia': (['data-asia/raw/Asia_15m-1B.xls'], ['companies_pool_all.json', 'companies_pool_nonfinancial.json']),
    'data-micro': (['data-micro/raw/Europe_0-15m.xls'], ['companies_pool_all.json', 'companies_pool_nonfinancial.json']),
}


def read_raw(path):
    sh = xlrd.open_workbook(str(ROOT / path)).sheet_by_name('Screening')
    out = {}
    for r in range(8, sh.nrows):
        row = sh.row_values(r)
        t = row[1]
        if not t:
            continue
        h = []
        for c in DIV_COLS:
            v = row[c]
            h.append(None if (v == '-' or v == '' or not isinstance(v, (int, float))) else round(abs(v), 3))
        out[t] = h
    return out


def main():
    for folder, (raws, pools) in REGIONS.items():
        raw = {}
        for rp in raws:
            raw.update(read_raw(rp))
        for pf in pools:
            p = ROOT / folder / pf
            if not p.exists():
                continue
            pool = json.load(open(p))
            hit = miss = agree = 0
            for c in pool:
                h = raw.get(c['ticker'])
                if h is None:
                    c['divHist'] = None
                    miss += 1
                    continue
                c['divHist'] = h
                hit += 1
                n = c.get('nRevPeriods') or 0
                if n:
                    paid = sum(1 for v in h[-n:] if v is not None and v > 0) / n
                    agree += abs(paid - (c.get('divPct') or 0)) < 0.011
            json.dump(pool, open(p, 'w'), ensure_ascii=False)
            print(f'{folder}/{pf}: {hit} with history, {miss} not in extract; stored divPct matches paid-share for {agree}/{hit}')


if __name__ == '__main__':
    main()
