"""Per-region biggest rank movers between the OLD market-cap valuation lenses and the LIVE EV-based lenses,
with the drivers behind each move (lens percentiles, EV vs market cap, net debt, earnings basis).

Used by scripts/research/movers_report.py (PDF). Import: movers_data.analyse() -> {region: {...}}.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import scoring as S  # noqa: E402

REGIONS = [('Europe', 'data', 'companies_1000_scored.json', 250),
           ('USA & Canada', 'data-us', 'companies_pool_all.json', 250),
           ('Asia & Pacific', 'data-asia', 'companies_pool_all.json', 250),
           ('Europe micro', 'data-micro', 'companies_pool_all.json', 100)]
N_MOVERS = 12
LENS = ('A', 'B', 'C')


def _load(p, default):
    try:
        return json.load(open(p))
    except Exception:
        return default


def analyse():
    nd_full = {}
    for f in ('data', 'data-us', 'data-asia', 'data-micro'):
        nd_full.update(_load(ROOT / f / 'net_debt.json', {}).get('entries', {}))
    ND = S.net_debt_lookup()
    out = {}
    for label, folder, poolf, window in REGIONS:
        pool = json.load(open(ROOT / folder / poolf))
        ov = json.load(open(ROOT / folder / 'mc_overrides_applied.json'))
        gmo = S.load_overrides()[1] if folder == 'data' else {}
        dl = {k for k in _load(ROOT / folder / 'delisted.json', {}) if not k.startswith('_')}
        distress = {k: v for k, v in _load(ROOT / folder / 'distress_flags.json', {}).items() if not k.startswith('_')}
        sc, _ = S.score_pool(pool, ov, gmo)
        # OLD lenses (market cap, last-year average NI)
        A1, B1, C1, A2, B2, C2 = [], [], [], [], [], []
        for c, r in zip(pool, sc):
            mc, gm = r['mc'], r['gm']
            a_new, b_new, c_new, _ = S.lenses(c, mc, gm)
            g = min(max(c['revGrowth'] or 0, 0), 2.0)
            A1.append((mc / c['revLTM']) / gm if gm and gm > 0 and c['revLTM'] else None)
            B1.append(b_new)
            C1.append((c['avgNI'] / mc) * (1 + g) if c['avgNI'] is not None and mc else None)
            A2.append(a_new); B2.append(b_new); C2.append(c_new)
        rows = []
        for i, (c, r) in enumerate(zip(pool, sc)):
            if c['ticker'] in dl:
                continue
            p_old = [S.percentile_rank(A1, i, False), S.percentile_rank(B1, i, False), S.percentile_rank(C1, i, True)]
            p_new = [S.percentile_rank(A2, i, False), S.percentile_rank(B2, i, False), S.percentile_rank(C2, i, True)]
            v_old = max([p for p in p_old if p is not None], default=0) / 100 * 18
            v_new = r['val_pts']
            nd = ND.get(c['ticker'])
            e = nd_full.get(c['ticker']) or {}
            mc = r['mc']
            ev = S.enterprise_value(mc, nd)
            ni3 = S.ni_3y(c)
            rows.append(dict(
                t=c['ticker'], n=c['name'], co=c['country'], ind=c.get('industry'), fin=bool(c.get('is_financial_sector')),
                mc=mc, nd=nd, ev=ev, evmc=(ev / mc if mc else None), has_nd=nd is not None, tier=e.get('tier'),
                nd_flags=e.get('flags') or [], nd_src=e.get('sourceType'), nd_date=e.get('balanceSheetDate'),
                capped=bool(nd is not None and mc and nd < -S.NET_CASH_CAP * mc),
                gm=r['gm'], rev=c['revLTM'], eq=c['equity'], ni1=c['avgNI'], ni3=ni3, g=c['revGrowth'],
                p_old=p_old, p_new=p_new, val_old=v_old, val_new=v_new,
                tot_old=r['total'] - v_new + v_old, tot_new=r['total'],
                distress=(distress.get(c['ticker']) or {}).get('level'),
                thesis=(c.get('thesis') or {}).get('business_description') if isinstance(c.get('thesis'), dict) else None,
            ))
        for key, tk in (('r_old', 'tot_old'), ('r_new', 'tot_new')):
            for k, x in enumerate(sorted(rows, key=lambda x: -x[tk]), 1):
                x[key] = k
        for x in rows:
            x['move'] = x['r_old'] - x['r_new']        # + = rose
            x['best_old'] = LENS[max(range(3), key=lambda k: -1 if x['p_old'][k] is None else x['p_old'][k])]
            x['best_new'] = LENS[max(range(3), key=lambda k: -1 if x['p_new'][k] is None else x['p_new'][k])]
        cand = [x for x in rows if min(x['r_old'], x['r_new']) <= window]
        up = sorted([x for x in cand if x['move'] > 0], key=lambda x: -x['move'])[:N_MOVERS]
        down = sorted([x for x in cand if x['move'] < 0], key=lambda x: x['move'])[:N_MOVERS]
        s_old = {x['t'] for x in rows if x['r_old'] <= 50}
        s_new = {x['t'] for x in rows if x['r_new'] <= 50}
        moved = [abs(x['move']) for x in rows]
        out[label] = dict(
            n=len(rows), window=window, nd_n=sum(x['has_nd'] for x in rows), up=up, down=down,
            overlap50=len(s_old & s_new), rose_n=sum(x['move'] > 0 for x in rows), fell_n=sum(x['move'] < 0 for x in rows),
            median_abs=sorted(moved)[len(moved) // 2], mean_abs=sum(moved) / len(moved),
            capped_n=sum(x['capped'] for x in rows),
            top50_old=sorted([x for x in rows if x['r_old'] <= 50], key=lambda x: x['r_old']),
            top50_new=sorted([x for x in rows if x['r_new'] <= 50], key=lambda x: x['r_new']),
        )
    return out


if __name__ == '__main__':
    res = analyse()
    for k, v in res.items():
        print('##', k, {a: v[a] for a in ('n', 'nd_n', 'overlap50', 'rose_n', 'fell_n', 'median_abs', 'capped_n')})
        for side in ('up', 'down'):
            print(' ', side)
            for x in v[side]:
                print(f"   {x['n'][:28]:28} {x['r_old']:>4}->{x['r_new']:<4} {x['move']:+5d} ev/mc {x['evmc'] and round(x['evmc'], 2)} nd {x['nd'] and round(x['nd'], 1)} "
                      f"ni1 {x['ni1'] and round(x['ni1'], 1)} ni3 {x['ni3'] and round(x['ni3'], 1)} lens {x['best_old']}->{x['best_new']} "
                      f"p_old {[None if p is None else round(p) for p in x['p_old']]} p_new {[None if p is None else round(p) for p in x['p_new']]} {x['distress'] or ''}")
