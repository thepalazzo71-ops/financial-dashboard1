"""v6 fixedPts computation for the USA/Canada pool, using the exact same
formulas as the European model (scripts/scoring.py's gm_band_points/
lenses/percentile_rank/score_pool are reused directly, unchanged) - the
Methodology sheet in data-us/raw/*_Shortlist_1.xlsx documents an
identical v6 model applied to this universe.
"""
from scoring import apply_profitability_bonus


def dilution_points(dilution):
    """Same banding as Europe's (reverse-engineered from data, matches the
    Methodology sheet's 'full marks <=10%; linear decay to 0 at 100%'
    description loosely - Europe's exact piecewise curve is used here
    since it's the proven, validated implementation)."""
    if dilution is None:
        return None
    d = dilution
    if d <= 0.10:
        return 12.0
    if d <= 0.15:
        return 12.0 - (d - 0.10) * 72.0
    if d <= 0.20:
        return 8.4 - (d - 0.15) * 168.0
    return 0.0


def revenue_growth_points(growth):
    if growth is None:
        return 0.0
    g = min(max(growth, 0.0), 3.0)
    return (g ** 0.4) / (3.0 ** 0.4) * 6.0


def compute_fixed_pts(c):
    """Returns (fixedPts dict, fixedSumNoGm) for a company dict with
    revGrowth, revConsistency, dilution, profitPct, cfoPct, nRevPeriods,
    divPct, gm, revHist already populated (see scripts/ingest_us_pool.py).

    profitability applies apply_profitability_bonus() - a company already
    in the top gross-margin band with long-term revenue growth that stays
    cash-generative overall gets this topped up to 16.0 regardless of the
    raw profitPct sign-only measure (added 2026-10-12, see
    docs/handoff-brief.md)."""
    profitability = round(c['profitPct'] * 16.0, 4)
    profitability = apply_profitability_bonus(profitability, c.get('gm'), c['cfoPct'], c['revHist'])
    pts = {
        'revenue_growth': round(revenue_growth_points(c['revGrowth']), 4),
        'revenue_consistency': round(c['revConsistency'] * 12.0, 4),
        'dilution': round(dilution_points(c['dilution']), 4) if c['dilution'] is not None else None,
        'profitability': profitability,
        'cfo_positive': round(c['cfoPct'] * 6.0, 4),
        'track_record': round((c['nRevPeriods'] / 10.0) * 8.0, 4),
        'dividend_consistency': round(c['divPct'] * 4.0, 4),
    }
    fixed_sum_no_gm = sum(v for v in pts.values() if v is not None)
    return pts, round(fixed_sum_no_gm, 4)
