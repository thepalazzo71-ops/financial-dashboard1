"""Merge a Europe-micro gross-margin round (docs/research-prompts/micro_gm_instructions.md) into data-micro pools.
Usage: python3 scripts/merge_micro_gm.py <out.json> [...]   Sanity: gm in (-0.5, 1.0), source must be a visible URL; official sources
(annual_report/results_announcement/filing_data_page) count as verified, aggregator ones are kept but unverified.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import us_scoring as U

D = Path(__file__).resolve().parent.parent / 'data-micro'
OFFICIAL = {'annual_report', 'results_announcement', 'filing_data_page', 'company_statement'}


def main(files):
    res = {}
    for f in files:
        res.update(json.load(open(f)))
    log_p = D / 'gm_research_log.json'
    log = json.load(open(log_p)) if log_p.exists() else {'results': {}}
    applied, cnt = {}, {}
    for t, v in res.items():
        gm = v.get('gm')
        good = v.get('status') == 'ok' and isinstance(gm, (int, float)) and -0.5 < gm < 1.0 and v.get('source_url')
        cnt['ok' if good else (v.get('status') or 'not_found')] = cnt.get('ok' if good else (v.get('status') or 'not_found'), 0) + 1
        log['results'][t] = {k: v.get(k) for k in ('status', 'gm', 'fiscal_year', 'currency', 'revenue', 'gross_profit', 'source_url', 'source_type', 'notes')}
        if good:
            applied[t] = v
    for p in ('companies_pool_all.json', 'companies_pool_nonfinancial.json'):
        pool = json.load(open(D / p))
        for c in pool:
            v = applied.get(c['ticker'])
            if not v:
                continue
            c['gm'] = round(float(v['gm']), 4); c['gmFiscalYear'] = v.get('fiscal_year'); c['gmSourceUrl'] = v.get('source_url')
            c['gmSourceType'] = v.get('source_type'); c['gmIsVerified'] = v.get('source_type') in OFFICIAL
            c['fixedPts'], c['fixedSumNoGm'] = U.compute_fixed_pts(c)
        json.dump(pool, open(D / p, 'w'))
    json.dump(log, open(log_p, 'w'), indent=1, ensure_ascii=False)
    print('gm round:', cnt, '| applied', len(applied))


if __name__ == '__main__':
    main(sys.argv[1:])
