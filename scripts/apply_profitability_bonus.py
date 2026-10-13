"""Idempotent (re)computation of the gross-margin + long-term-revenue-growth
+ CFO-positive profitability bonus (scoring.apply_profitability_bonus) for
every company in both pools.

For each company the baseline is always the raw sign-only measure,
round(profitPct * 16, 4); the bonus is then applied on top, and
fixedPts['profitability'], fixedSumNoGm and the profitabilityBonusApplied
flag are set to match. Safe to re-run any number of times.

First run 2026-10-12. Re-run 2026-10-13 after discovering the history
slots are one YEAR apart (Capital IQ LTM offsets are in quarters), not 4
months - which had made every CAGR 3x too high and over-awarded the bonus
(see docs/handoff-brief.md).

Usage: python3 scripts/apply_profitability_bonus.py
"""
import json
from pathlib import Path

from scoring import apply_profitability_bonus, full_history_cagr

ROOT = Path(__file__).resolve().parent.parent


def correct_file(path, label):
    companies = json.load(open(path))
    gained, lost, kept, drifted = [], [], [], []
    for c in companies:
        raw = round(c['profitPct'] * 16.0, 4)
        current = c['fixedPts']['profitability']
        was_bonused = bool(c.get('profitabilityBonusApplied'))
        if not was_bonused and abs(current - raw) > 1e-6:
            drifted.append((c['ticker'], current, raw))
            continue
        new_pts = apply_profitability_bonus(raw, c.get('gm'), c.get('cfoPct'), c['revHist'])
        now_bonused = new_pts != raw
        if abs(new_pts - current) > 1e-9:
            c['fixedSumNoGm'] = round(c['fixedSumNoGm'] - current + new_pts, 4)
            c['fixedPts']['profitability'] = new_pts
        if now_bonused:
            c['profitabilityBonusApplied'] = True
        else:
            c.pop('profitabilityBonusApplied', None)
        rec = (c['ticker'], c['name'], raw, new_pts, full_history_cagr(c['revHist']))
        if now_bonused and not was_bonused:
            gained.append(rec)
        elif was_bonused and not now_bonused:
            lost.append(rec)
        elif now_bonused:
            kept.append(rec)
    json.dump(companies, open(path, 'w'))
    print(f'{label}: bonus now applies to {len(kept) + len(gained)} of {len(companies)} '
          f'(kept {len(kept)}, gained {len(gained)}, removed {len(lost)}; '
          f'{len(drifted)} untouched with unexpected profitability pts)')
    return gained, lost, kept, drifted


def main():
    for p, label in [(ROOT / 'data' / 'companies_1000_scored.json', 'Europe'),
                     (ROOT / 'data-us' / 'companies_pool_all.json', 'US all-sector'),
                     (ROOT / 'data-us' / 'companies_pool_nonfinancial.json', 'US non-financial')]:
        correct_file(p, label)

    d = json.load(open(ROOT / 'data' / 'companies_1000_scored.json'))
    proc = next(c for c in d if c['ticker'] == 'LSE:PROC')
    cagr = full_history_cagr(proc['revHist'])
    print(f"\nProCook check: profitability pts = {proc['fixedPts']['profitability']}, "
          f"fixedSumNoGm = {proc['fixedSumNoGm']}, bonusApplied = {proc.get('profitabilityBonusApplied')}, "
          f"CAGR = {cagr:.1%}" if cagr is not None else '')


if __name__ == '__main__':
    main()
