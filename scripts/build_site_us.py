"""Build the USA/Canada dashboard (site/template_us.html + data-us/*.json
-> docs/us.html). Same static-site pattern as scripts/build_site.py, same
v6 model (scripts/scoring.py, unchanged) - the only structural difference
is that this market has TWO parallel pools (all-sector vs non-financial,
built by scripts/ingest_us_pool.py from a separate 499/276-survivor
universe) switched via an in-page toggle instead of Europe's single pool.

No live mc/gm override files exist yet for this market (no refresh cycle
has run) - mc_overrides/gm_overrides are empty dicts, so "live" and
"baseline" are identical for now, same starting state Europe had before
its first market-cap refresh batch.

Usage: python3 scripts/build_site_us.py
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from scoring import gm_band_points, median_gm_points, score_pool

ROOT = Path(__file__).resolve().parent.parent
DATA_US = ROOT / "data-us"
TEMPLATE = ROOT / "site" / "template_us.html"
OUT = ROOT / "docs" / "us.html"

LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')


def parse_links(md):
    if not md:
        return []
    return [{'label': label, 'url': url} for label, url in LINK_RE.findall(md)]


def build_sector_payload(companies):
    """No overrides exist yet for this market - mc/gm are both baseline."""
    scored, median_gm_pts = score_pool(companies, {}, {})
    out = []
    for c, s in zip(companies, scored):
        gm_links = []
        if c.get('thesis') and c['thesis'].get('website'):
            pass
        out.append({
            't': c['ticker'], 'n': c['name'], 'co': c['country'],
            'mc0': round(s['mc'], 2), 'mcRefreshed': False, 'mcUpdatedAt': None, 'mcSource': None,
            'eq': c['equity'], 'revLTM': c['revLTM'], 'revGrowth': c['revGrowth'],
            'dilution': c['dilution'], 'dilutionDataMissing': c.get('dilutionDataMissing', False),
            'profitPct': c['profitPct'], 'cfoPct': c['cfoPct'], 'divPct': c['divPct'],
            'nRevPeriods': c['nRevPeriods'], 'revConsistency': c['revConsistency'],
            'avgNI': c['avgNI'],
            'gm0': s['gm'], 'gmIsOverride': False,
            'gmFY': c['thesis'].get('fiscal_year') if c.get('thesis') else None,
            'gmSrcType': 'verified_filing' if c.get('gmIsVerified') else None,
            'gmLinks': [],
            'fixedPts': c['fixedPts'], 'fixedSumNoGm': c['fixedSumNoGm'],
            'revHist': c['revHist'], 'niHist': c['niHist'],
            'thesis': c.get('thesis'),
            'industry': c.get('industry'), 'archetypePrecomputed': c.get('archetype'),
            'newsNote': None,
        })
    rows_for_history = sorted(
        [{'t': c['ticker'], 'n': c['name'], 'co': c['country'], 'rank': i + 1,
          'mc': round(s['mc'], 2), 'pb': (round(s['mc'] / c['equity'], 3) if c['equity'] else None),
          'roe': round(s['roe'], 4) if s['roe'] is not None else None,
          'rg': round(c['revGrowth'], 4) if c['revGrowth'] is not None else None,
          'gm': s['gm'], 'gmFb': s['gm_is_fallback'], 'total': s['total'],
          'pts': {'rg': c['fixedPts']['revenue_growth'], 'rc': c['fixedPts']['revenue_consistency'],
                  'dl': c['fixedPts']['dilution'], 'vl': round(s['val_pts'], 2),
                  'pf': c['fixedPts']['profitability'], 'cfo': c['fixedPts']['cfo_positive'],
                  'tr': c['fixedPts']['track_record'], 'dv': c['fixedPts']['dividend_consistency'],
                  'gm': round(s['gm_pts'], 2)}}
         for i, (c, s) in enumerate(sorted(zip(companies, scored), key=lambda cs: -cs[1]['total']))],
        key=lambda r: r['rank'])
    return {
        'companies': out, 'median_gm_pts': round(median_gm_pts, 4),
        'history': {'baseline': rows_for_history}, 'historyDates': ['baseline'],
        'poolSize': len(companies),
    }


def main():
    all_sector = json.load(open(DATA_US / "companies_pool_all.json"))
    nonfin = json.load(open(DATA_US / "companies_pool_nonfinancial.json"))

    payload = {
        'sectors': {
            'all': build_sector_payload(all_sector),
            'nonfinancial': build_sector_payload(nonfin),
        },
        'corporateActions': {'tender_offers': [], 'mergers_acquisitions': [], 'spinoffs': [], 'other': []},
    }
    build_info = {
        'buildDate': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        'poolSizeAll': len(all_sector), 'poolSizeNonFinancial': len(nonfin),
    }

    template = TEMPLATE.read_text()
    html = template.replace('__PAYLOAD_JSON__', json.dumps(payload, separators=(',', ':')))
    html = html.replace('__BUILD_INFO_JSON__', json.dumps(build_info))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html)
    print(f"built {OUT} ({len(html)/1024:.0f} KB, all-sector={len(all_sector)}, non-financial={len(nonfin)})")


if __name__ == '__main__':
    main()
