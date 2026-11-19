"""BigBen Interactive (ENXTPA:BIG): correct stale Capital IQ fundamentals with the FY to 31 Mar 2026 results.

The 17 Mar 2026 Capital IQ extract predates BigBen's FY2025/26 results. Those show a EUR 237.4m net loss and
shareholders' equity of EUR -21.0m (EUR -55.8m including minorities), according to the Yahoo Finance fundamentals
feed, annual balance sheet 2026-03-31. Company-reported net debt was EUR 167.9m, including EUR 59.1m of bonds,
after a bond default in Feb 2026. Nacon (56.7% owned) has been in judicial reorganisation since 2 Mar 2026, and
BigBen has been in accelerated safeguard since 17 Aug 2026.

With the stale EUR 366m equity, lens B (P/B vs ROE) made BigBen look extremely cheap. This script:
  * sets equity to EUR -21.0m in USD, so lens B no longer applies (negative book);
  * replaces the last niHist slot with the FY2025/26 net income (EUR -237.4m) and recomputes avgNI
    (mean of the last four slots, as at ingest);
  * refreshes the market cap to the latest close x 18.5m shares (the shares on the 2026-03-31 balance sheet).
Idempotent. Re-run after any re-ingest of the micro pool.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import price_stats as PS  # noqa: E402

T = 'ENXTPA:BIG'
FX = 1.10023105            # EUR/USD used for the net-debt record (fetched 2026-11-19)
EQUITY_EUR = -21.0
NI_FY26_EUR = -237.4
SHARES_M = 18.5
NOTE = ('Capital IQ fundamentals corrected with FY to 31 Mar 2026 results (Yahoo Finance fundamentals feed): '
        'net loss EUR 237.4m, shareholders\' equity EUR -21.0m (EUR -55.8m incl. minorities); company-reported net debt '
        'EUR 167.9m incl. EUR 59.1m bonds. Bond default Feb 2026; accelerated safeguard since 17 Aug 2026; restructuring '
        'expected to heavily dilute or wipe out existing shareholders.')

for f in ('companies_pool_all.json', 'companies_pool_nonfinancial.json'):
    p = ROOT / 'data-micro' / f
    pool = json.load(open(p))
    for c in pool:
        if c['ticker'] != T:
            continue
        c['equity'] = round(EQUITY_EUR * FX, 1)
        c['niHist'][-1] = round(NI_FY26_EUR * FX, 1)
        last4 = [v for v in c['niHist'][-4:] if v is not None]
        c['avgNI'] = sum(last4) / len(last4)
        c['dataCorrection'] = NOTE
        print(f, 'equity', c['equity'], 'avgNI', round(c['avgNI'], 1))
    json.dump(pool, open(p, 'w'), ensure_ascii=False)

px = PS.px_for(T)
ov_p = ROOT / 'data-micro' / 'mc_overrides_applied.json'
ov = json.load(open(ov_p))
mc = SHARES_M * px['l'] * FX
ov[T] = {'mc': round(mc, 3), 'computed': True, 'updatedAt': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
         'quoteDate': px['d'], 'source': f"computed: {SHARES_M:g}m shares (Yahoo balance sheet 2026-03-31) x last close "
         f"{px['l']:g} EUR ({px['d']})", 'shares': SHARES_M, 'price': px['l'], 'cur': 'EUR', 'fx': FX,
         'local': f"EUR {SHARES_M * px['l']:.2f}m"}
json.dump(ov, open(ov_p, 'w'))
print('market cap USD m', round(mc, 2))

nd_p = ROOT / 'data-micro' / 'net_debt.json'
nd = json.load(open(nd_p))
e = nd['entries'][T]
if 'company-reported net debt EUR 167.9m' not in e['notes']:
    e['notes'] += (' Confirmed against the company: FY2025/26 results report net debt of EUR 167.9m (incl. EUR 59.1m bonds) '
                   'and cash of EUR 31.6m at 31 Mar 2026; the company is in accelerated safeguard (bond default Feb 2026).')
e['mcUsd'] = round(mc, 1)
e['evUsd'] = round(mc + e['netDebtUsd'], 1)
json.dump(nd, open(nd_p, 'w'), indent=1, ensure_ascii=False)
print('net debt note updated')
