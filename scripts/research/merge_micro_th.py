"""Merge a Europe-micro thesis round (docs/research-prompts/micro_th_instructions.md) into data-micro pools.
Usage: python3 scripts/merge_micro_th.py <out.json> [...]   ({ticker: {thesis: {six fields}, notes}}); prints notes that mention takeovers/delistings."""
import json, re, sys
from pathlib import Path

D = Path(__file__).resolve().parent.parent / 'data-micro'
F = ("business_description", "competitive_position", "main_shareholders", "red_flags", "website", "insider_ownership")


def main(files):
    res = {}
    for f in files:
        res.update(json.load(open(f)))
    ok = {t: v['thesis'] for t, v in res.items() if v.get('thesis') and all(k in v['thesis'] for k in F) and v['thesis']['business_description']}
    for p in ('companies_pool_all.json', 'companies_pool_nonfinancial.json'):
        pool = json.load(open(D / p)); n = 0
        for c in pool:
            if c['ticker'] in ok:
                c['thesis'] = {k: ok[c['ticker']][k] for k in F}; c['hasThesis'] = True; n += 1
        json.dump(pool, open(D / p, 'w')); print(p, n)
    print('merged', len(ok), 'of', len(res))
    for t, v in res.items():
        n = v.get('notes') or ''
        if re.search(r'takeover|tender|privati|delist|suspend|squeeze|insolv|bankrupt|liquidat|restructur|going concern', n, re.I) and not re.match(r'\s*no (takeover|tender|delist)', n, re.I):
            print('CHECK', t, '|', n[:300])


if __name__ == '__main__':
    main(sys.argv[1:])
