#!/usr/bin/env python3
"""Fetch ~5 years of daily closes from Yahoo's chart API for every ticker in the
four dashboard pools and keep only a compact summary per ticker
(data-prices/price_stats.json):

  sym      Yahoo symbol used          cur   quote currency (GBp = pence)
  last     last close                 lastDate
  hi/hiDate  5y closing high          lo/loDate  5y closing low
  jmp/jmpDate  biggest one-day close ratio (data-glitch / redenomination detector)
  n        number of daily closes     first   first date in window
  name     Yahoo's name for the symbol  nm   0..1 name-match score vs our name
  via      'map' | 'search' (how the symbol was resolved)

Closes are split-adjusted (Yahoo `close`), not dividend-adjusted, so they match
the price a user sees on a quote page.  Percentages derived from them are
currency-neutral.  Resumable: tickers already in the output file are skipped
(use --refresh to redo).  Only one host is needed: query1.finance.yahoo.com.

  python3 scripts/fetch_price_history.py [--limit N] [--region eu|micro|asia|us]
                                         [--workers 4] [--refresh]
"""
import argparse, json, os, re, sys, time, threading, urllib.parse, urllib.request, difflib
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data-prices', 'price_stats.json')
POOLS = {
    'eu':    'data/companies_1000_scored.json',
    'micro': 'data-micro/companies_pool_all.json',
    'asia':  'data-asia/companies_pool_all.json',
    'us':    'data-us/companies_pool_all.json',
}
# CapIQ-style exchange prefix -> Yahoo suffix ('' = none)
SUFFIX = {
    'WSE': '.WA', 'ENXTPA': '.PA', 'XTRA': '.DE', 'OM': '.ST', 'AIM': '.L', 'LSE': '.L',
    'BIT': '.MI', 'ATSE': '.AT', 'HLSE': '.HE', 'CPSE': '.CO', 'BVB': '.RO', 'BME': '.MC',
    'DB': '.DE', 'ZGSE': '.ZA', 'BUL': '.SO', 'SWX': '.SW', 'ENXTBR': '.BR', 'OB': '.OL',
    'NSEL': '.VS', 'ENXTAM': '.AS', 'BUSE': '.BD', 'WBAG': '.VI', 'ICSE': '.IC',
    'ENXTLS': '.LS', 'TLSE': '.TL', 'BST': '.BE', 'XSAT': '.ST', 'RISE': '.RG', 'NGM': '.ST',
    'SEP': '.PR', 'ISE': '.IR', 'HMSE': '.HM', 'BRSE': '.BE', 'DUSE': '.DU', 'JSE': '.JO',
    'MUN': '.MU', 'TSX': '.TO', 'TSXV': '.V', 'TSE': '.T', 'KOSDAQ': '.KQ', 'KOSE': '.KS',
    'SEHK': '.HK', 'SGX': '.SI', 'Catalist': '.SI', 'ASX': '.AX', 'NZSE': '.NZ', 'NSE': '.NS',
    'TWSE': '.TW', 'TPEX': '.TWO', 'NasdaqGS': '', 'NasdaqGM': '', 'NasdaqCM': '',
    'NYSE': '', 'NYSEAM': '', 'OTCPK': '',
}
# exchanges whose Yahoo symbol is the CapIQ symbol with share-class spaces -> '-'
JP_LIKE = {'TSE', 'SPSE', 'FKSE', 'NSE'}   # Japan regional boards -> all trade as .T
UA = {'User-Agent': 'Mozilla/5.0'}
HOST = 'https://query1.finance.yahoo.com'
_lock = threading.Lock()


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429:
                time.sleep(5 * (i + 1))
                continue
            time.sleep(1.5 * (i + 1))
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def candidates(ticker):
    ex, _, sym = ticker.partition(':')
    sym = sym.strip()
    if not sym or ex == '-':
        return []
    out = []
    if ex in ('SPSE', 'FKSE', 'NSE') and re.fullmatch(r'[0-9A-Z]{4}', sym):
        out.append(sym + '.T')            # Sapporo/Fukuoka/Nagoya listings trade on TSE too
        sfx = {'SPSE': '.S', 'FKSE': '.F', 'NSE': '.NG'}[ex]
        out.append(sym + sfx)
        return out
    if ex == 'SEHK':
        digits = re.sub(r'\D', '', sym)
        if digits:
            out.append(digits.zfill(4) + '.HK')
        return out
    if ex in ('KOSDAQ', 'KOSE'):
        sym = re.sub(r'^A(?=\d{6}$)', '', sym)      # CapIQ 'A006280' -> '006280'
        out.append(sym + SUFFIX[ex])
        out.append(sym + (SUFFIX['KOSE'] if ex == 'KOSDAQ' else SUFFIX['KOSDAQ']))
        return out
    sfx = SUFFIX.get(ex)
    if sfx is None:
        return []
    s = sym.replace('/', '-').replace(' ', '-')
    if ex in ('TSX', 'TSXV'):
        s = s.replace('.', '-')           # LAS.A -> LAS-A.TO
    elif sfx == '':
        if '.' in s:                      # BRK.B -> BRK-B (NYSE style) and BRKB (OTC / Nasdaq style)
            out.append(s.replace('.', ''))
            s = s.replace('.', '-')
    elif ex in ('XTRA', 'DB', 'BST', 'BRSE', 'HMSE', 'DUSE', 'MUN'):
        pass
    out.append(s + sfx)
    if ex in ('XTRA', 'DB'):
        out.append(s + ('.DE' if sfx != '.DE' else '.F'))
    if ex in ('AIM', 'LSE') and s.endswith('.'):
        out.append(s.rstrip('.') + sfx)
    return out


def norm(n):
    n = n.lower()
    n = re.sub(r'[^a-z0-9 ]+', ' ', n)
    n = re.sub(r'\b(co|corp|corporation|inc|ltd|limited|plc|ag|sa|se|nv|ab|asa|as|oyj|spa|sas|holdings?|holding|group|the|company|kabushiki|kaisha|kk|tbk|bhd|pcl|public|s a|s p a|a s|n v|d d|a d|ad|sp z o o|zrt|nyrt|hf|oy|a g)\b', ' ', n)
    return ' '.join(n.split())


def name_score(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    ta, tb = set(a.split()), set(b.split())
    jac = len(ta & tb) / max(1, len(ta | tb))
    seq = difflib.SequenceMatcher(None, a, b).ratio()
    pre = 1.0 if (a.startswith(b[:5]) or b.startswith(a[:5])) else 0.0
    return round(max(jac, seq, 0.85 * pre), 3)


def chart(sym):
    url = f'{HOST}/v8/finance/chart/{urllib.parse.quote(sym)}?range=5y&interval=1d&events=div%2Csplit'
    d = get(url)
    try:
        r = d['chart']['result'][0]
    except Exception:
        return None
    ts = r.get('timestamp') or []
    cl = (r.get('indicators', {}).get('quote') or [{}])[0].get('close') or []
    pts = [(t, c) for t, c in zip(ts, cl) if c is not None and c > 0]
    if len(pts) < 5:
        return None
    meta = r.get('meta', {})
    return meta, pts


def fix_unit_switches(pts):
    """Yahoo sometimes flips a London series between GBP and pence (x100 / x0.01 overnight).
    Rescale everything before such a day so the series is continuous."""
    pts = list(pts)
    for i in range(len(pts) - 1, 0, -1):
        r = pts[i][1] / pts[i - 1][1]
        for f in (100.0, 0.01):
            if abs(r / f - 1) < 0.15:
                pts[:i] = [(t, c * f) for t, c in pts[:i]]
                break
    return pts


def summarise(sym, meta, pts, ourname, via):
    if sym.endswith('.L'):
        pts = fix_unit_switches(pts)
    d = lambda t: time.strftime('%Y-%m-%d', time.gmtime(t))
    hi = max(pts, key=lambda p: p[1])
    lo = min(pts, key=lambda p: p[1])
    last = pts[-1]
    nm = meta.get('longName') or meta.get('shortName') or ''
    jmp, jd = 1.0, None                         # biggest one-day close-to-close ratio (either direction)
    for (t0, c0), (t1, c1) in zip(pts, pts[1:]):
        rr = max(c1 / c0, c0 / c1)
        if rr > jmp:
            jmp, jd = rr, d(t1)
    return {'jmp': round(jmp, 2), 'jmpDate': jd,
        'sym': sym, 'cur': meta.get('currency'), 'last': round(last[1], 6), 'lastDate': d(last[0]),
        'hi': round(hi[1], 6), 'hiDate': d(hi[0]), 'lo': round(lo[1], 6), 'loDate': d(lo[0]),
        'n': len(pts), 'first': d(pts[0][0]), 'name': nm, 'nm': name_score(ourname, nm), 'via': via,
    }


GERMAN = {'XTRA', 'DB', 'BST', 'BRSE', 'HMSE', 'DUSE', 'MUN'}
GER_SFX = ('.DE', '.SG', '.F', '.MU', '.HM', '.BE', '.DU', '.HA', '.BM')


def sym_ok_for(sym, ex):
    """A search hit must sit on the ticker's own market (no foreign secondary quotes)."""
    sfx = SUFFIX.get(ex)
    if sfx is None:
        return False
    if ex in GERMAN:
        return sym.endswith(GER_SFX)
    if sfx == '':
        return '.' not in sym
    if ex in ('SPSE', 'FKSE') or (ex in JP_LIKE and sfx == '.NS'):
        return sym.endswith('.T')
    return sym.endswith(sfx)


def search(ourname, ticker):
    ex = ticker.partition(':')[0]
    q = urllib.parse.quote(re.sub(r'\s+', ' ', ourname))
    d = get(f'{HOST}/v1/finance/search?q={q}&quotesCount=6&newsCount=0')
    res = []
    for it in (d or {}).get('quotes', []):
        if it.get('quoteType') in ('EQUITY', None) and it.get('symbol') and sym_ok_for(it['symbol'], ex):
            nm = it.get('longname') or it.get('shortname') or ''
            res.append((name_score(ourname, nm), it['symbol']))
    res.sort(reverse=True)
    return [s for sc, s in res if sc >= 0.6][:2]


def process(c):
    t, name = c['ticker'], c['name']
    for sym in candidates(t):
        r = chart(sym)
        if r:
            s = summarise(sym, r[0], r[1], name, 'map')
            if s['nm'] >= 0.5:
                return t, s
            s['via'] = 'map-lowname'
            fallback = s
            break
    else:
        fallback = None
    for sym in search(name, t):
        r = chart(sym)
        if r:
            s = summarise(sym, r[0], r[1], name, 'search')
            if s['nm'] >= 0.6:
                return t, s
    return t, fallback          # may be None -> no data / low-confidence kept for audit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int)
    ap.add_argument('--region')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--refresh', action='store_true')
    a = ap.parse_args()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    have = {} if a.refresh or not os.path.exists(OUT) else json.load(open(OUT))
    todo = []
    for reg, f in POOLS.items():
        if a.region and reg != a.region:
            continue
        for c in json.load(open(os.path.join(ROOT, f))):
            if c['ticker'] not in have and c['ticker'] != '-' and not any(c['ticker'] == x['ticker'] for x in todo):
                todo.append(c)
    if a.limit:
        todo = todo[:a.limit]
    print(f'{len(todo)} to fetch, {len(have)} cached', flush=True)
    done = miss = 0
    t0 = time.time()
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(process, c): c for c in todo}
        for f in as_completed(futs):
            c = futs[f]
            try:
                t, s = f.result()
            except Exception as e:
                t, s = c['ticker'], None
            with _lock:
                have[t] = s
                done += 1
                miss += s is None
                if done % 100 == 0 or done == len(todo):
                    json.dump(have, open(OUT, 'w'), separators=(',', ':'))
                    print(f'{done}/{len(todo)} miss={miss} {time.time()-t0:.0f}s', flush=True)
    json.dump(have, open(OUT, 'w'), separators=(',', ':'))


if __name__ == '__main__':
    main()
