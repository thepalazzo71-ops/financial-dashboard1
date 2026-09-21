"""Build the standalone dashboard (site/template.html + data/*.json -> docs/index.html).

No server, no database, no claude.ai dependency: this produces one
self-contained HTML file with the scored pool baked in. Run this after any
change to data/companies_1000_scored.json, data/mc_overrides_applied.json,
or data/gm_overrides_applied.json, then commit docs/index.html (or let the
"Build dashboard" GitHub Action do it automatically on push).

Also resyncs data/companies_1000_scored.json's own valPts/total/rankFull
against whatever overrides are currently applied, so that file (and
anything reading it, like scripts/snapshot.py or a batch-selection query)
never drifts from what the live dashboard actually shows - see
scoring.resync_pool_ranks for why this matters.

Usage: python3 scripts/build_site.py
"""
import json
import re
from datetime import datetime, timezone

from scoring import DATA, ROOT, compact_snapshot_rows, load_companies, load_overrides, resync_pool_ranks, score_pool

TEMPLATE = ROOT / "site" / "template.html"
OUT = ROOT / "docs" / "index.html"
POOL_PATH = DATA / "companies_1000_scored.json"
NEWS_PATH = DATA / "company_news.json"
SNAPSHOTS = ROOT / "snapshots"

LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')


def parse_links(md):
    if not md:
        return []
    return [{'label': label, 'url': url} for label, url in LINK_RE.findall(md)]


def load_company_news():
    """ticker -> {note, confidence, ...}: a short, factual one-liner on any
    *fundamental* event (earnings, M&A, guidance, contract, regulatory...)
    identified as a plausible cause of a company's rank move since the
    baseline. Manually researched, not automated - see docs/handoff-brief.md.
    A missing ticker means no attributable catalyst was found, which is a
    normal and expected outcome (most rank moves are pool ripple or a plain
    re-rating with no distinct news event), not a gap to fill in.
    """
    if not NEWS_PATH.exists():
        return {}
    with open(NEWS_PATH) as f:
        return json.load(f)


def load_history(companies):
    """History entries for the dashboard's history dropdown.

    'baseline' is always computed fresh here - zero market-cap/GM
    overrides, against the current (already dilution-corrected) pool -
    rather than read from a dated file. That's deliberate: any snapshot
    file captured mid-project could predate a since-fixed data bug (see
    the 2026-09-21 dilution fix in docs/handoff-brief.md, which briefly
    had ProCook Group at rank 511 instead of its true ~77) and would
    misrepresent the "before this refresh project" state if used as-is.
    Real dated snapshots/shortlist_snapshot_<date>.json files (captured
    going forward, after that fix) are loaded normally alongside it.

    Returns (history dict keyed by date/'baseline', ordered key list with
    'baseline' first).
    """
    history = {'baseline': compact_snapshot_rows(companies, {}, {})}
    dated_keys = []
    for path in sorted(SNAPSHOTS.glob("shortlist_snapshot_*.json")):
        date_str = path.stem.replace("shortlist_snapshot_", "")
        with open(path) as f:
            history[date_str] = json.load(f)
        dated_keys.append(date_str)
    return history, ['baseline'] + dated_keys


def build_payload(companies, mc_overrides, gm_overrides):
    scored, median_gm_pts = score_pool(companies, mc_overrides, gm_overrides)
    company_news = load_company_news()

    out_companies = []
    for c, s in zip(companies, scored):
        mc_o = mc_overrides.get(c['ticker'])
        gm_o = gm_overrides.get(c['ticker'])
        news = company_news.get(c['ticker'])
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
            'newsNote': news.get('note') if news else None,
        })

    history, history_dates = load_history(companies)
    payload = {
        'median_gm_pts': round(median_gm_pts, 4), 'companies': out_companies,
        'history': history, 'historyDates': history_dates,
    }
    build_info = {
        'buildDate': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        'poolSize': len(companies),
        'mcRefreshedCount': len(mc_overrides),
        'gmOverrideCount': len(gm_overrides),
    }
    return payload, build_info


def main():
    companies = load_companies()
    mc_overrides, gm_overrides = load_overrides()

    resync_pool_ranks(companies, mc_overrides, gm_overrides)
    with open(POOL_PATH, 'w') as f:
        json.dump(companies, f)

    payload, build_info = build_payload(companies, mc_overrides, gm_overrides)
    template = TEMPLATE.read_text()
    html = template.replace('__PAYLOAD_JSON__', json.dumps(payload, separators=(',', ':')))
    html = html.replace('__BUILD_INFO_JSON__', json.dumps(build_info))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html)
    print(f"resynced ranks for {len(companies)} companies; "
          f"built {OUT} ({len(html)/1024:.0f} KB, {build_info['poolSize']} companies, "
          f"{build_info['mcRefreshedCount']} mc overrides, {build_info['gmOverrideCount']} gm overrides)")


if __name__ == '__main__':
    main()
