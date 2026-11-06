#!/usr/bin/env python3
"""Fill in market caps for companies that have no researched/refreshed one, from price history.

The Capital IQ extracts carry each company's market cap (USD) as of the extract date.  Checked against
shares x Yahoo close x FX the extract date is 2026-03-17 (median error <0.1%, spread ~0.2%).  So

    market cap now = extract market cap x (close now x FX now) / (close on 2026-03-17 x FX on 2026-03-17)

with closes from Yahoo's chart API (symbols resolved by scripts/fetch_price_history.py, stored in
data-prices/price_stats.json) and FX from Yahoo's `<CUR>USD=X` series.  Closes are split-adjusted, so
corporate splits do not distort it; what it cannot see is a change in the share count since March
(rights issues, buybacks) - those caps are only as good as that assumption.

Writes into <folder>/mc_overrides_applied.json ONLY for tickers that have no entry yet (researched caps are
never overwritten), tagged `derived: true`.  Re-run with --refresh to recompute the derived ones.

  python3 scripts/derive_market_caps.py --region asia [--limit N] [--refresh] [--dry-run]
"""
import argparse, json, os, sys, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_price_history as F
import price_stats as PS

ROOT = Path(__file__).resolve().parent.parent
EXTRACT_DATE = '2026-03-17'
REGIONS = {'asia': 'data-asia', 'micro': 'data-micro', 'us': 'data-us', 'eu': 'data'}
MAX_STALE_DAYS = 45
MIN_RATIO, MAX_RATIO = 0.04, 25.0     # reject absurd moves (bad data / unadjusted splits)


def series(sym):
    d = F.get(f"{F.HOST}/v8/finance/chart/{urllib.parse.quote(sym)}?range=1y&interval=1d")
    try:
        r = d['chart']['result'][0]
        cl = r['indicators']['quote'][0]['close']
        s = {time.strftime('%Y-%m-%d', time.gmtime(t)): c for t, c in zip(r['timestamp'], cl) if c and c > 0}
        return s, r['meta'].get('currency')
    except Exception:
        return None, None


def at_or_before(s, day, max_back=10):
    ds = sorted(x for x in s if x <= day)
    if not ds:
        return None
    from datetime import date
    if (date.fromisoformat(day) - date.fromisoformat(ds[-1])).days > max_back:
        return None
    return ds[-1], s[ds[-1]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--region', required=True, choices=list(REGIONS))
    ap.add_argument('--limit', type=int)
    ap.add_argument('--refresh', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--workers', type=int, default=5)
    a = ap.parse_args()
    folder = ROOT / REGIONS[a.region]
    pool_file = folder / ('companies_1000_scored.json' if a.region == 'eu' else 'companies_pool_all.json')
    pool = json.load(open(pool_file))
    ov_path = folder / 'mc_overrides_applied.json'
    ov = json.load(open(ov_path)) if ov_path.exists() else {}
    dl_path = folder / 'delisted.json'
    delisted = {k for k in (json.load(open(dl_path)) if dl_path.exists() else {}) if not k.startswith('_')}
    stats = PS._load()
    todo = []
    for c in pool:
        t = c['ticker']
        if t in delisted or t in PS.REJECT:
            continue
        have = ov.get(t)
        if have and not (a.refresh and have.get('derived')):
            continue
        v = stats.get(t)
        if not v or v['n'] < PS.MIN_OBS or v.get('jmp', 1) >= PS.MAX_JUMP or (v['via'] == 'search' and v['nm'] < PS.MIN_NAME):
            continue
        todo.append((c, v))
    if a.limit:
        todo = todo[:a.limit]
    print(f'{len(todo)} candidates ({len(ov)} existing overrides in {folder.name})', flush=True)

    fx_cache, lock = {}, __import__('threading').Lock()

    def fx_series(cur):
        base = 'GBP' if cur == 'GBp' else cur
        if base == 'USD':
            return None
        with lock:
            if base in fx_cache:
                return fx_cache[base]
        s, _ = series(base + 'USD=X')
        with lock:
            fx_cache[base] = s
        return s

    def work(item):
        c, v = item
        s, cur = series(v['sym'])
        if not s:
            return c['ticker'], None, 'no series'
        cur = cur or v['cur']
        pt = at_or_before(s, EXTRACT_DATE)
        last_d = max(s)
        if pt is None:
            return c['ticker'], None, 'no close near extract date'
        ref_last = PS.as_of()
        from datetime import date
        if ref_last and (date.fromisoformat(ref_last) - date.fromisoformat(last_d)).days > MAX_STALE_DAYS:
            return c['ticker'], None, 'stale'
        fxs = fx_series(cur)
        scale = 0.01 if cur == 'GBp' else 1.0
        if fxs is None:
            fx_t = fx_n = 1.0
        else:
            ft, fn = at_or_before(fxs, EXTRACT_DATE), at_or_before(fxs, last_d)
            if not ft or not fn:
                return c['ticker'], None, 'no fx'
            fx_t, fx_n = ft[1] * scale, fn[1] * scale
        ratio = (s[last_d] * fx_n) / (pt[1] * fx_t)
        if not (MIN_RATIO <= ratio <= MAX_RATIO):
            return c['ticker'], None, f'ratio {ratio:.2f}'
        mc0 = c['mc0'] if 'mc0' in c else c['mc']
        return c['ticker'], {
            'mc': round(mc0 * ratio, 3), 'derived': True,
            'source': f'derived: extract market cap x price/FX change since {EXTRACT_DATE} (Yahoo daily closes, {v["sym"]})',
            'updatedAt': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'quoteDate': last_d,
            'local': f'{cur} {s[last_d]:g}', 'ratio': round(ratio, 4), 'extractMc': mc0,
        }, 'ok'

    res, why = {}, {}
    t0 = time.time()
    with ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(work, it) for it in todo]
        for i, f in enumerate(as_completed(futs), 1):
            try:
                t, rec, st = f.result()
            except Exception as e:
                continue
            if rec:
                res[t] = rec
            else:
                why[st.split()[0]] = why.get(st.split()[0], 0) + 1
            if i % 200 == 0:
                print(f'{i}/{len(todo)} ok={len(res)} {time.time()-t0:.0f}s', flush=True)
    print(f'derived {len(res)}; skipped: {why}')
    if a.dry_run:
        return res
    ov.update(res)
    json.dump(ov, open(ov_path, 'w'))   # compact, same format as the other writers
    print('wrote', ov_path)
    return res


if __name__ == '__main__':
    main()
