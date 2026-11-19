#!/usr/bin/env python3
"""Net debt from Yahoo Finance's fundamentals time-series (the feed behind its balance-sheet pages).

  python3 scripts/fetch_yahoo_net_debt.py --region asia --tickers T1 T2 ...      (or --tickers-file list.json)
          [--replace-weak] [--dry-run]

For each ticker (Yahoo symbol from data-prices/price_stats.json) it takes the LATEST balance-sheet date on which
total debt and cash are both reported and builds, on that one date:
    gross debt (ex leases) = TotalDebt - CapitalLeaseObligations   (leases kept separately, as in the researched entries)
    cash                   = CashCashEquivalentsAndShortTermInvestments (else CashAndCashEquivalents)
    net debt               = gross debt - cash
in the company's REPORTING currency (which can differ from the trading currency, e.g. HK-listed companies reporting
in CNY), converted to USD at today's Yahoo FX.  Yahoo's own NetDebt (when published) is kept as a cross-check, and the
share count (OrdinarySharesNumber) is stored for later market-cap work.

Writes tier-'A' entries tagged sourceType 'data_feed' into <folder>/net_debt.json:
  * tickers with no usable entry -> added
  * with --replace-weak: tickers whose existing entry is an undated or aggregator figure -> replaced
  * entries from company filings / results releases are never replaced (a disagreement is only printed)
Balance sheets before 2025-06-30 are ignored (same rule as scripts/merge_net_debt.py).
"""
import argparse, json, sys, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_price_history as F
import derive_market_caps as D
import price_stats as PS

ROOT = Path(__file__).resolve().parent.parent
FOLDERS = {'asia': 'data-asia', 'eu': 'data', 'us': 'data-us', 'micro': 'data-micro'}
STALE_BEFORE = '2025-06-30'
FIELDS = ['TotalDebt', 'CapitalLeaseObligations', 'CashCashEquivalentsAndShortTermInvestments', 'CashAndCashEquivalents',
          'NetDebt', 'MinorityInterest', 'OrdinarySharesNumber', 'StockholdersEquity']
STRONG_SOURCES = {'annual_report', 'quarterly_report', 'earnings_release', 'exchange_filing', 'company_filing', 'results_announcement'}


def fetch(sym):
    types = ','.join([p + f for p in ('quarterly', 'annual') for f in FIELDS])
    q = urllib.parse.quote(sym)
    d = F.get(f'{F.HOST}/ws/fundamentals-timeseries/v1/finance/timeseries/{q}?symbol={q}&type={types}'
              f'&period1=1704067200&period2={int(time.time()) + 86400}')
    series = {}
    for res in ((d or {}).get('timeseries') or {}).get('result') or []:
        k = res['meta']['type'][0]
        for v in res.get(k) or []:
            if v and v.get('reportedValue') and v['reportedValue'].get('raw') is not None:
                series.setdefault(k, {})[v['asOfDate']] = (v['reportedValue']['raw'], v.get('currencyCode'))
    return series


def build(series):
    """Pick one balance-sheet date (quarterly first, else annual) where debt and cash both exist."""
    for per in ('quarterly', 'annual'):
        debt = series.get(per + 'TotalDebt', {})
        cash = series.get(per + 'CashCashEquivalentsAndShortTermInvestments') or {}
        cash_basic = series.get(per + 'CashAndCashEquivalents') or {}
        dates = sorted(set(debt) & (set(cash) | set(cash_basic)), reverse=True)
        if not dates:
            continue
        dt = dates[0]
        td, cur = debt[dt]
        c, cash_basis = (cash[dt][0], 'cash + short-term investments') if dt in cash else (cash_basic[dt][0], 'cash and equivalents only')
        lease = (series.get(per + 'CapitalLeaseObligations') or {}).get(dt, (None,))[0]
        gross = td - (lease or 0)
        g = lambda f: (series.get(per + f) or {}).get(dt, (None,))[0]
        m = lambda x: None if x is None else round(x / 1e6, 2)
        return {'date': dt, 'period': 'quarter' if per == 'quarterly' else 'annual', 'currency': cur,
                'gross_debt': m(gross), 'lease': m(lease), 'cash': m(c), 'cash_basis': cash_basis,
                'net_debt': m(gross - c), 'yahoo_net_debt': m(g('NetDebt')), 'minority_interest': m(g('MinorityInterest')),
                'shares_mm': m(g('OrdinarySharesNumber')), 'equity': m(g('StockholdersEquity')),
                'lease_found': lease is not None}
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--region', required=True, choices=list(FOLDERS))
    ap.add_argument('--tickers', nargs='*', default=[])
    ap.add_argument('--tickers-file')
    ap.add_argument('--replace-weak', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    tickers = list(a.tickers)
    if a.tickers_file:
        tickers += [x['ticker'] if isinstance(x, dict) else x for x in json.load(open(a.tickers_file))]
    folder = ROOT / FOLDERS[a.region]
    pool_file = folder / ('companies_1000_scored.json' if a.region == 'eu' else 'companies_pool_all.json')
    pool = {c['ticker']: c for c in json.load(open(pool_file))}
    mc_o = json.load(open(folder / 'mc_overrides_applied.json'))
    out_path = folder / 'net_debt.json'
    doc = json.load(open(out_path)) if out_path.exists() else {'entries': {}}
    entries = doc.setdefault('entries', {})
    stats = PS._load()
    fx_cache = {}

    def fx(cur):
        if cur == 'USD':
            return 1.0
        if cur not in fx_cache:
            s, _ = D.series(cur + 'USD=X')
            fx_cache[cur] = round(s[max(s)], 8) if s else None
        return fx_cache[cur]

    def work(t):
        v = stats.get(t)
        syms = [v['sym']] if v else []
        syms += [s for s in F.candidates(t) if s not in syms]      # no price history: try the mapped symbols
        if not syms:
            return t, None, 'no Yahoo symbol'
        r = None
        for sym in syms:
            r = build(fetch(sym))
            if r:
                v = {'sym': sym}
                break
        if not r:
            return t, None, 'no balance sheet in feed'
        if r['date'] < STALE_BEFORE:
            return t, None, f'balance sheet too old ({r["date"]})'
        r['sym'] = v['sym']
        return t, r, 'ok'

    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(work, dict.fromkeys(tickers)))
    n_add = n_rep = n_keep = 0
    why = {}
    checks = []
    today = date.today().isoformat()
    for t, r, st in results:
        if not r:
            why[st.split(' (')[0]] = why.get(st.split(' (')[0], 0) + 1
            continue
        rate = fx(r['currency'])
        if rate is None:
            why['no FX'] = why.get('no FX', 0) + 1
            continue
        old = entries.get(t)
        weak = old is None or old.get('tier') not in ('A', 'B') or not old.get('balanceSheetDate') or old.get('balanceSheetDate') == 'unknown' \
            or old.get('sourceType') in (None, 'aggregator', 'data_feed')
        if old and old.get('tier') == 'F':
            n_keep += 1
            continue
        if old and old.get('tier') in ('A', 'B') and old.get('netDebtUsd') is not None:
            new_usd = r['net_debt'] * rate
            checks.append((t, pool[t]['name'][:26], round(old['netDebtUsd'], 1), round(new_usd, 1), old.get('balanceSheetDate'), r['date'], old.get('sourceType')))
            if not weak or not a.replace_weak:
                n_keep += 1
                continue
        mc = (mc_o.get(t) or {}).get('mc') or pool[t].get('mc0')
        nd_usd = r['net_debt'] * rate
        flags = []
        if not r['lease_found']:
            flags.append('lease liabilities not separated in the feed (debt may include leases)')
        if r['cash_basis'] != 'cash + short-term investments':
            flags.append('cash excludes short-term investments')
        if r['date'] < '2026-03-31':
            flags.append('balance sheet older than Q1 2026')
        mi_usd = (r['minority_interest'] or 0) * rate
        if mc and mi_usd > 0.25 * mc:
            flags.append(f'large minority interests (${mi_usd:,.0f}M): consolidated debt/cash include partly-owned subsidiaries; EV here excludes minorities')
        if mc and nd_usd > 3 * mc:
            flags.append('net debt > 3x market cap (highly leveraged)')
        elif mc and nd_usd < -3 * mc:
            flags.append('net cash > 3x market cap - check cash definition')
        e = {'tier': 'A', 'currency': r['currency'], 'balanceSheetDate': r['date'], 'periodType': r['period'],
             'grossDebt': r['gross_debt'], 'cash': r['cash'], 'leaseLiabilities': r['lease'], 'netDebtReported': r['yahoo_net_debt'],
             'netDebt': r['net_debt'], 'netDebtUsd': round(nd_usd, 1), 'fx': rate, 'minorityInterest': r['minority_interest'],
             'mcUsd': round(mc, 1) if mc else None, 'evUsd': round(mc + nd_usd, 1) if mc else None,
             'sourceUrl': f"https://finance.yahoo.com/quote/{r['sym']}/balance-sheet/", 'sourceType': 'data_feed',
             'notes': f"Yahoo Finance fundamentals feed ({r['period']} balance sheet {r['date']}, {r['currency']} m): total debt minus leases "
                      f"{r['gross_debt']:g}, {r['cash_basis']} {r['cash']:g}"
                      + (f"; Yahoo's own net debt (cash and equivalents only) {r['yahoo_net_debt']:g}" if r['yahoo_net_debt'] is not None else '')
                      + f". Minority interests {r['minority_interest']}. Shares {r['shares_mm']}m. Fetched {today}.",
             'sharesMm': r['shares_mm'], 'flags': flags}
        if r['lease'] is not None and mc:
            e['evInclLeasesUsd'] = round(mc + nd_usd + r['lease'] * rate, 1)
        if old is None or old.get('tier') not in ('A', 'B'):
            n_add += 1
        else:
            n_rep += 1
        entries[t] = e
    print(f'tickers {len(tickers)} | added {n_add} | replaced weak {n_rep} | kept existing {n_keep} | skipped {why}')
    if checks:
        agree = sum(1 for c in checks if abs(c[2] - c[3]) <= max(0.2 * abs(c[2]), 2))
        print(f'cross-check vs existing researched entries: {agree}/{len(checks)} within 20% (or $2M)')
        for c in checks:
            if abs(c[2] - c[3]) > max(0.2 * abs(c[2]), 2):
                print('   differs:', c)
    if a.dry_run:
        return
    doc['_generated'] = today
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    print('wrote', out_path)


if __name__ == '__main__':
    main()
