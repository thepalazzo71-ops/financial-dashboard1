#!/usr/bin/env python3
"""Dividend history from Yahoo Finance for companies whose Capital IQ extract has NO dividend data (divHist all null).

  python3 scripts/fetch_yahoo_dividends.py --region asia [--tickers T1 T2 ...] [--all-missing] [--refresh]

Two Yahoo feeds per company (symbol from data-prices/price_stats.json, else the mapped candidates, as in fetch_yahoo_net_debt.py):
  * fundamentals time-series  annualCashDividendsPaid   -> cash paid per fiscal year (reporting currency, ~4 years) -> converted to USD
  * chart API (range=max, events=div)                    -> every dividend payment date/amount per share (long history)

Each of the 10 history slots (the same 10 annual trailing-12-month points as niHist; slot 9 = LTM at the extract date
2026-03-17, slot k = k-9 years before) gets
    flag   1 / 0   = a dividend payment fell in that 12-month window (or the cash-flow figure is > 0) / none did
    amount USD m   = cash dividends paid when a fiscal-year figure lies within 6 months of the slot's end date, else null
Writes <folder>/dividends_yahoo.json (resumable; entries kept unless --refresh).  Merge with scripts/merge_dividends.py.
"""
import argparse, json, sys, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_price_history as F
import derive_market_caps as D
import price_stats as PS

ROOT = Path(__file__).resolve().parent.parent
FOLDERS = {'asia': 'data-asia', 'eu': 'data', 'us': 'data-us', 'micro': 'data-micro'}
EXTRACT = date(2026, 3, 17)
N_SLOTS = 10


def slot_end(k):
    y = EXTRACT.year - (N_SLOTS - 1 - k)
    try:
        return EXTRACT.replace(year=y)
    except ValueError:
        return EXTRACT.replace(year=y, day=28)


def fetch_cash(sym):
    q = urllib.parse.quote(sym)
    d = F.get(f'{F.HOST}/ws/fundamentals-timeseries/v1/finance/timeseries/{q}?symbol={q}&type=annualCashDividendsPaid'
              f'&period1=1262304000&period2={int(time.time()) + 86400}')
    out = []
    for res in ((d or {}).get('timeseries') or {}).get('result') or []:
        for v in res.get('annualCashDividendsPaid') or []:
            if v and v.get('reportedValue') and v['reportedValue'].get('raw') is not None:
                out.append((v['asOfDate'], abs(v['reportedValue']['raw']), v.get('currencyCode')))
    return sorted(out)


def fetch_events(sym):
    d = F.get(f'{F.HOST}/v8/finance/chart/{urllib.parse.quote(sym)}?range=max&interval=3mo&events=div')
    try:
        r = d['chart']['result'][0]
    except Exception:
        return None
    evs = (r.get('events') or {}).get('dividends') or {}
    out = sorted((datetime.fromtimestamp(v['date'], timezone.utc).date(), v['amount']) for v in evs.values())
    first_ts = (r.get('meta') or {}).get('firstTradeDate')
    first = datetime.fromtimestamp(first_ts, timezone.utc).date() if first_ts else None
    return out, (r.get('meta') or {}).get('currency'), first


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--region', required=True, choices=list(FOLDERS))
    ap.add_argument('--tickers', nargs='*', default=[])
    ap.add_argument('--refresh', action='store_true')
    ap.add_argument('--limit', type=int)
    a = ap.parse_args()
    folder = ROOT / FOLDERS[a.region]
    pool_file = folder / ('companies_1000_scored.json' if a.region == 'eu' else 'companies_pool_all.json')
    pool = json.load(open(pool_file))
    out_path = folder / 'dividends_yahoo.json'
    doc = json.load(open(out_path)) if out_path.exists() else {}
    targets = a.tickers or [c['ticker'] for c in pool if not any(v is not None for v in (c.get('divHist') or []))]
    if not a.refresh:
        targets = [t for t in targets if t not in doc]
    if a.limit:
        targets = targets[:a.limit]
    stats = PS._load()
    fx_cache = {}

    def fx(cur):
        if not cur or cur == 'USD':
            return 1.0
        base = 'GBP' if cur == 'GBp' else cur
        if base not in fx_cache:
            s, _ = D.series(base + 'USD=X')
            fx_cache[base] = s[max(s)] if s else None
        r = fx_cache[base]
        return None if r is None else (r / 100 if cur == 'GBp' else r)

    def work(t):
        v = stats.get(t)
        syms = [v['sym']] if v else []
        syms += [s for s in F.candidates(t) if s not in syms]
        for sym in syms:
            ev = fetch_events(sym)
            if ev is None:
                continue
            events, tcur, first = ev
            cash = fetch_cash(sym)
            return t, dict(sym=sym, events=events, tcur=tcur, first=first, cash=cash)
        return t, None

    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(work, targets))
    got = miss = 0
    for t, r in results:
        if r is None:
            doc[t] = {'status': 'no Yahoo symbol / chart'}
            miss += 1
            continue
        flags, amounts = [], []
        for k in range(N_SLOTS):
            end = slot_end(k)
            start = end - timedelta(days=365)
            paid = any(start < d <= end for d, _ in r['events'])
            flags.append(1 if paid else 0)
            amounts.append(None)
        annual = []
        for d_s, raw, cur in r['cash']:
            rate = fx(cur)
            usd = None if rate is None else raw * rate / 1e6
            annual.append({'date': d_s, 'cur': cur, 'local_m': round(raw / 1e6, 3), 'usd_m': None if usd is None else round(usd, 3)})
            d0 = date.fromisoformat(d_s)
            k = min(range(N_SLOTS), key=lambda k: abs((slot_end(k) - d0).days))
            if abs((slot_end(k) - d0).days) <= 183 and usd is not None:
                if amounts[k] is None or abs((slot_end(k) - d0).days) < amounts[k][1]:
                    amounts[k] = (round(usd, 3), abs((slot_end(k) - d0).days))
                if usd > 0:
                    flags[k] = 1
        doc[t] = {'status': 'ok', 'sym': r['sym'], 'flags': flags, 'amounts': [None if x is None else x[0] for x in amounts],
                  'annual': annual, 'nEvents': len(r['events']), 'lastEvent': str(r['events'][-1][0]) if r['events'] else None,
                  'firstTrade': str(r['first']) if r['first'] else None, 'fetched': date.today().isoformat()}
        got += 1
    json.dump(doc, open(out_path, 'w'), indent=0, ensure_ascii=False)
    payers = sum(1 for t, r in results if r and doc[t].get('flags') and doc[t]['flags'][-1])
    withamt = sum(1 for t, r in results if r and any(x is not None for x in doc[t]['amounts']))
    print(f'{a.region}: {len(targets)} companies | fetched {got} | no symbol {miss} | paid a dividend in the latest slot {payers} | with cash amounts {withamt}')


if __name__ == '__main__':
    main()
