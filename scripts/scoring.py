"""Shared v6 scoring logic, used by both scripts/snapshot.py (xlsx snapshots)
and scripts/build_site.py (the static dashboard). Keeping this in one place
means the snapshot and the live dashboard can never silently drift apart.

See docs/handoff-brief.md for the methodology this implements.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load_companies():
    return json.load(open(DATA / "companies_1000_scored.json"))


def load_overrides():
    """Returns (mc_overrides, gm_overrides), each {ticker: {...}}."""
    mc = json.load(open(DATA / "mc_overrides_applied.json"))
    gm_path = DATA / "gm_overrides_applied.json"
    gm = json.load(open(gm_path)) if gm_path.exists() else {}
    return mc, gm


def gm_band_points(gm):
    if gm is None:
        return None
    if gm >= 0.60:
        return 18.0
    if gm >= 0.50:
        return 15.3
    if gm >= 0.40:
        return 12.6
    if gm >= 0.30:
        return 9.9
    if gm >= 0.20:
        return 7.2
    if gm >= 0.10:
        return 4.5
    if gm >= 0.05:
        return 1.8
    return 0.0


def median_gm_points(companies):
    pts = sorted(gm_band_points(c['gm']) for c in companies if c['gm'] is not None)
    n = len(pts)
    if n == 0:
        return 0.0
    return pts[n // 2] if n % 2 else (pts[n // 2 - 1] + pts[n // 2]) / 2


def effective_mc(c, mc_overrides):
    o = mc_overrides.get(c['ticker'])
    return o['mc'] if o and 'mc' in o else c['mc0']


def effective_gm(c, gm_overrides):
    """Returns (gm, is_override, is_fallback)."""
    o = gm_overrides.get(c['ticker'])
    if o and 'gm' in o:
        return o['gm'], True, False
    if c['gm'] is not None:
        return c['gm'], False, False
    return None, False, True


def lenses(c, mc, gm):
    A = B = C = None
    if gm is not None and gm > 0 and c['revLTM']:
        A = (mc / c['revLTM']) / gm
    roe = (c['avgNI'] / c['equity']) if (c['avgNI'] is not None and c['equity']) else None
    if c['equity'] and c['equity'] > 0 and roe is not None:
        B = (mc / c['equity']) / max(roe / 0.10, 0.1)
    if c['avgNI'] is not None and mc:
        g = min(max(c['revGrowth'] or 0, 0), 2.0)
        C = (c['avgNI'] / mc) * (1 + g)
    return A, B, C, roe


def percentile_rank(values, idx, higher_better):
    v = values[idx]
    if v is None:
        return None
    others = [x for x in values if x is not None]
    n = len(others)
    if n <= 1:
        return 100.0
    beat = sum(1 for x in others if (x < v if higher_better else x > v))
    return 100.0 * beat / (n - 1)


def score_pool(companies, mc_overrides, gm_overrides):
    """Scores every company against the full pool. Returns a list of dicts,
    one per company (same order as `companies`), each augmented with:
    mc, gm, gm_is_override, gm_is_fallback, roe, val_pts, gm_pts, total, pb.
    """
    median_gm_pts = median_gm_points(companies)

    mcs, gms, gm_meta = [], [], []
    for c in companies:
        mc = effective_mc(c, mc_overrides)
        gm, is_override, is_fallback = effective_gm(c, gm_overrides)
        mcs.append(mc)
        gms.append(gm)
        gm_meta.append((is_override, is_fallback))

    A_list, B_list, C_list, ROE_list = [], [], [], []
    for c, mc, gm in zip(companies, mcs, gms):
        a, b, cc, roe = lenses(c, mc, gm)
        A_list.append(a)
        B_list.append(b)
        C_list.append(cc)
        ROE_list.append(roe)

    results = []
    for i, c in enumerate(companies):
        pA = percentile_rank(A_list, i, False)
        pB = percentile_rank(B_list, i, False)
        pC = percentile_rank(C_list, i, True)
        best = max([p for p in [pA, pB, pC] if p is not None], default=0)
        val_pts = best / 100 * 18
        gm = gms[i]
        gm_pts = gm_band_points(gm) if gm is not None else median_gm_pts
        total = round(c['fixedSumNoGm'] + gm_pts + val_pts, 2)
        pb = mcs[i] / c['equity'] if c['equity'] else None
        is_override, is_fallback = gm_meta[i]
        results.append({
            'mc': mcs[i], 'gm': gm, 'gm_is_override': is_override, 'gm_is_fallback': is_fallback,
            'roe': ROE_list[i], 'pb': pb, 'val_pts': val_pts, 'gm_pts': gm_pts, 'total': total,
        })

    return results, median_gm_pts


def compact_snapshot_rows(companies, mc_overrides, gm_overrides):
    """Compact per-company records (rank, mc, pts breakdown, ...) for the
    dashboard's history feature and for before/after movers analysis.

    Pass {} / {} for mc_overrides/gm_overrides to get the *baseline* state
    (original market caps, no refresh-project overrides applied) - the
    correct "before" point for comparisons, since it's always freshly
    computed from the current (dilution-corrected) pool rather than read
    from a dated file that might predate a since-fixed data bug.
    """
    scored, _ = score_pool(companies, mc_overrides, gm_overrides)
    rows = []
    for c, s in zip(companies, scored):
        rows.append({
            't': c['ticker'], 'n': c['name'], 'co': c['country'],
            'mc': round(s['mc'], 2),
            'pb': round(s['pb'], 3) if s['pb'] else None,
            'roe': round(s['roe'], 4) if s['roe'] is not None else None,
            'rg': round(c['revGrowth'], 4) if c['revGrowth'] is not None else None,
            'gm': s['gm'], 'gmFb': s['gm_is_fallback'], 'total': s['total'],
            'pts': {
                'rg': c['fixedPts']['revenue_growth'], 'rc': c['fixedPts']['revenue_consistency'],
                'dl': c['fixedPts']['dilution'], 'vl': round(s['val_pts'], 2),
                'pf': c['fixedPts']['profitability'], 'cfo': c['fixedPts']['cfo_positive'],
                'tr': c['fixedPts']['track_record'], 'dv': c['fixedPts']['dividend_consistency'],
                'gm': round(s['gm_pts'], 2),
            },
        })
    rows.sort(key=lambda r: -r['total'])
    for i, r in enumerate(rows):
        r['rank'] = i + 1
    return rows


def resync_pool_ranks(companies, mc_overrides, gm_overrides):
    """Recomputes valPts/gmPtsUsed/fixedSum/total/rankFull for every company
    in place, using currently-applied overrides. Does NOT touch mc0/gm
    baselines - only the derived fields, so this can be re-run any time
    overrides change to keep the stored pool in sync with what the live
    dashboard (which does this same computation in-browser) shows.

    Call this after every override batch, not just after a model fix -
    percentile-ranked valuation means every company's val_pts can shift
    slightly whenever any single company's effective market cap changes.

    Returns the companies list, re-sorted by total descending (rankFull
    assigned to match).
    """
    scored, _ = score_pool(companies, mc_overrides, gm_overrides)
    for c, s in zip(companies, scored):
        c['gmPtsUsed'] = round(s['gm_pts'], 4)
        c['gmIsFallback'] = s['gm_is_fallback']
        c['valPts'] = round(s['val_pts'], 4)
        c['fixedSum'] = round(c['fixedSumNoGm'] + c['gmPtsUsed'], 4)
        c['total'] = round(c['fixedSum'] + c['valPts'], 4)

    companies.sort(key=lambda c: -c['total'])
    for i, c in enumerate(companies):
        c['rankFull'] = i + 1
    return companies
