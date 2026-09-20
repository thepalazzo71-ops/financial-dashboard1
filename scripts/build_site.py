"""Build the standalone dashboard (site/template.html + data/*.json -> docs/index.html).

No server, no database, no claude.ai dependency: this produces one
self-contained HTML file with the scored pool baked in. Run this after any
change to data/companies_1000_scored.json, data/mc_overrides_applied.json,
or data/gm_overrides_applied.json, then commit docs/index.html (or let the
"Build dashboard" GitHub Action do it automatically on push).

Usage: python3 scripts/build_site.py
"""
import json
import re
from datetime import datetime, timezone

from scoring import ROOT, load_companies, load_overrides, score_pool

TEMPLATE = ROOT / "site" / "template.html"
OUT = ROOT / "docs" / "index.html"

LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')


def parse_links(md):
    if not md:
        return []
    return [{'label': label, 'url': url} for label, url in LINK_RE.findall(md)]


def build_payload():
    companies = load_companies()
    mc_overrides, gm_overrides = load_overrides()
    scored, median_gm_pts = score_pool(companies, mc_overrides, gm_overrides)

    out_companies = []
    for c, s in zip(companies, scored):
        mc_o = mc_overrides.get(c['ticker'])
        gm_o = gm_overrides.get(c['ticker'])
        out_companies.append({
            't': c['ticker'], 'n': c['name'], 'co': c['country'],
            'mc0': round(s['mc'], 2),
            'mcRefreshed': c['ticker'] in mc_overrides,
            'mcUpdatedAt': mc_o.get('updatedAt') if mc_o else None,
            'mcSource': mc_o.get('source') if mc_o else None,
            'eq': c['equity'], 'revLTM': c['revLTM'], 'revGrowth': c['revGrowth'],
            'dilution': c['dilution'], 'profitPct': c['profitPct'], 'cfoPct': c['cfoPct'],
            'divPct': c['divPct'], 'nRevPeriods': c['nRevPeriods'], 'revConsistency': c['revConsistency'],
            'avgNI': c['avgNI'],
            'gm0': s['gm'],
            'gmIsOverride': s['gm_is_override'],
            'gmFY': gm_o.get('fiscalYear') if gm_o else c['gmFiscalYear'],
            'gmSrcType': 'manual_override' if gm_o else c['gmSourceType'],
            'gmLinks': parse_links(c.get('gmSourceUrl')),
            'fixedPts': c['fixedPts'], 'fixedSumNoGm': c['fixedSumNoGm'],
            'revHist': c['revHist'], 'niHist': c['niHist'],
            'thesis': c.get('thesis'),
        })

    payload = {'median_gm_pts': round(median_gm_pts, 4), 'companies': out_companies}
    build_info = {
        'buildDate': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        'poolSize': len(companies),
        'mcRefreshedCount': len(mc_overrides),
        'gmOverrideCount': len(gm_overrides),
    }
    return payload, build_info


def main():
    payload, build_info = build_payload()
    template = TEMPLATE.read_text()
    html = template.replace('__PAYLOAD_JSON__', json.dumps(payload, separators=(',', ':')))
    html = html.replace('__BUILD_INFO_JSON__', json.dumps(build_info))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html)
    print(f"built {OUT} ({len(html)/1024:.0f} KB, {build_info['poolSize']} companies, "
          f"{build_info['mcRefreshedCount']} mc overrides, {build_info['gmOverrideCount']} gm overrides)")


if __name__ == '__main__':
    main()
