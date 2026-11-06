"""Shared helpers for the 5-year price-range feature.

data-prices/price_stats.json is produced by scripts/fetch_price_history.py.
`px_for(ticker)` returns the compact record embedded in each dashboard payload
(or None when no usable price history exists); `inject(html, default_min_mc)`
splices the shared UI partials (site/partials/swingers.*) into a template so
the four dashboards share one implementation.
"""
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATS = ROOT / 'data-prices' / 'price_stats.json'
PARTIALS = ROOT / 'site' / 'partials'
MIN_OBS = 120          # fewer closes than this -> too little history to show
MAX_JUMP = 8           # a one-day close move of 8x+ = redenomination / bad data: drop the series
MIN_NAME = 0.45        # Yahoo name vs our name; below = probably the wrong security

# Yahoo symbols that resolve to a different security than ours (checked by hand)
REJECT = {'ENXTPA:CBSM', 'ENXTPA:CRI', 'NasdaqGM:SWKH', 'BRSE:SQL', 'BST:3WB'}

_cache = None


def _load():
    global _cache
    if _cache is None:
        _cache = json.load(open(STATS)) if STATS.exists() else {}
    return _cache


def as_of():
    dates = [v['lastDate'] for v in _load().values() if v]
    return max(dates) if dates else None


def px_for(ticker):
    v = _load().get(ticker)
    if not v or ticker in REJECT or v['n'] < MIN_OBS or (v['via'] == 'search' and v['nm'] < MIN_NAME) or v.get('jmp', 1) >= MAX_JUMP:
        return None
    ref = as_of()
    if ref and (date.fromisoformat(ref) - date.fromisoformat(v['lastDate'])).days > 45:
        return None      # stopped trading / delisted: a stale "current" price would mislead
    return {'l': v['last'], 'h': v['hi'], 'lo': v['lo'], 'hd': v['hiDate'], 'ld': v['loDate'],
            'd': v['lastDate'], 'f': v['first'], 'n': v['n'], 'cur': v['cur'], 's': v['sym']}


def attach(payload):
    """Add `px` to every company dict in a dashboard payload; returns coverage."""
    got = 0
    lists = [payload['companies']] if 'companies' in payload else [s['companies'] for s in payload['sectors'].values()]
    for lst in lists:
        for c in lst:
            c['px'] = px_for(c['t'])
        got = max(got, sum(c['px'] is not None for c in lst))
    payload['pxAsOf'] = as_of()
    return got


def inject(html, default_min_mc=10):
    html = html.replace('/*__SWINGERS_CSS__*/', (PARTIALS / 'swingers.css').read_text())
    html = html.replace('<!--__SWINGERS_HTML__-->', (PARTIALS / 'swingers.html').read_text())
    js = (PARTIALS / 'swingers.js').read_text().replace('__SW_DEFAULT_MINMC__', str(default_min_mc))
    return html.replace('/*__SWINGERS_JS__*/', js)
