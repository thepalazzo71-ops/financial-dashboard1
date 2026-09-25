"""Build the USA/Canada dashboard (site/template_us.html + data-us/*.json
-> docs/us.html). Same static-site pattern as scripts/build_site.py, same
v6 model (scripts/scoring.py, unchanged) - the only structural difference
is that this market has TWO parallel pools (all-sector vs non-financial,
built by scripts/ingest_us_pool.py from a separate 499/276-survivor
universe) switched via an in-page toggle instead of Europe's single pool.

mc_overrides/corporate_actions are shared across both sector pools (keyed
by ticker, not pool-specific) since a company's real-world market cap or
merger status doesn't depend on which sector view you're looking at it
from. gm_overrides is empty - no live GM refresh cycle has run yet for
this market (see docs/handoff-brief.md).

Usage: python3 scripts/build_site_us.py
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from scoring import compact_snapshot_rows, gm_band_points, median_gm_points, score_pool

ROOT = Path(__file__).resolve().parent.parent
DATA_US = ROOT / "data-us"
TEMPLATE = ROOT / "site" / "template_us.html"
OUT = ROOT / "docs" / "us.html"
MC_OVERRIDES_PATH = DATA_US / "mc_overrides_applied.json"
CORP_ACTIONS_PATH = DATA_US / "corporate_actions.json"

LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')


def parse_links(md):
    if not md:
        return []
    return [{'label': label, 'url': url} for label, url in LINK_RE.findall(md)]


def load_mc_overrides():
    if not MC_OVERRIDES_PATH.exists():
        return {}
    with open(MC_OVERRIDES_PATH) as f:
        return json.load(f)


def load_corporate_actions():
    if not CORP_ACTIONS_PATH.exists():
        return {'tender_offers': [], 'mergers_acquisitions': [], 'spinoffs': [], 'other': []}
    with open(CORP_ACTIONS_PATH) as f:
        return json.load(f)


def build_sector_payload(companies, mc_overrides):
    scored, median_gm_pts = score_pool(companies, mc_overrides, {})
    out = []
    for c, s in zip(companies, scored):
        mc_o = mc_overrides.get(c['ticker'])
        out.append({
            't': c['ticker'], 'n': c['name'], 'co': c['country'],
            'mc0': round(s['mc'], 2),
            'mcRefreshed': c['ticker'] in mc_overrides,
            'mcUpdatedAt': mc_o.get('updatedAt') if mc_o else None,
            'mcSource': mc_o.get('source') if mc_o else None,
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
    # 'baseline' is always computed fresh with zero overrides - the
    # "before this refresh project" state - never read off the (now
    # overridden) `scored` array above. Same convention as build_site.py's
    # load_history(); mirrored here after finding this had drifted (US
    # dashboard was accidentally showing baseline == live once real
    # mc_overrides existed, which flattened the Δ/history comparison).
    baseline_rows = compact_snapshot_rows(companies, {}, {})
    return {
        'companies': out, 'median_gm_pts': round(median_gm_pts, 4),
        'history': {'baseline': baseline_rows}, 'historyDates': ['baseline'],
        'poolSize': len(companies),
    }


def main():
    all_sector = json.load(open(DATA_US / "companies_pool_all.json"))
    nonfin = json.load(open(DATA_US / "companies_pool_nonfinancial.json"))
    mc_overrides = load_mc_overrides()

    payload = {
        'sectors': {
            'all': build_sector_payload(all_sector, mc_overrides),
            'nonfinancial': build_sector_payload(nonfin, mc_overrides),
        },
        'corporateActions': load_corporate_actions(),
    }
    build_info = {
        'buildDate': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        'poolSizeAll': len(all_sector), 'poolSizeNonFinancial': len(nonfin),
        'mcOverrideCount': len(mc_overrides),
    }

    template = TEMPLATE.read_text()
    html = template.replace('__PAYLOAD_JSON__', json.dumps(payload, separators=(',', ':')))
    html = html.replace('__BUILD_INFO_JSON__', json.dumps(build_info))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html)
    print(f"built {OUT} ({len(html)/1024:.0f} KB, all-sector={len(all_sector)}, non-financial={len(nonfin)}, "
          f"{len(mc_overrides)} mc overrides)")


if __name__ == '__main__':
    main()
