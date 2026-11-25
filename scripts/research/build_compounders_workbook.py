import json, sys
sys.path.insert(0, __import__('pathlib').Path(__file__).resolve().parents[1].as_posix())
import scoring as S
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE


def clean(v):
    return ILLEGAL_CHARACTERS_RE.sub('', v) if isinstance(v, str) else v

R = str(__import__('pathlib').Path(__file__).resolve().parents[2]) + '/'
F = 'Arial'


def L(p, d):
    try:
        return json.load(open(p))
    except Exception:
        return d


REGIONS = [  # label, folder, all-pool file, non-financial pool file (None = tier F in net_debt.json marks financials)
    ('Asia & Pacific', 'data-asia', 'companies_pool_all.json', 'companies_pool_nonfinancial.json'),
    ('Europe', 'data', 'companies_1000_scored.json', None),
    ('USA & Canada', 'data-us', 'companies_pool_all.json', 'companies_pool_nonfinancial.json'),
    ('Europe micro', 'data-micro', 'companies_pool_all.json', 'companies_pool_nonfinancial.json'),
]


def screen(label, folder, pf, nf):
    allp = json.load(open(R + f'{folder}/{pf}'))
    ov = json.load(open(R + f'{folder}/mc_overrides_applied.json'))
    gmo = S.load_overrides()[1] if folder == 'data' else {}
    nd = L(R + f'{folder}/net_debt.json', {}).get('entries', {})
    sc, _ = S.score_pool(allp, ov, gmo)
    by = {c['ticker']: (c, s) for c, s in zip(allp, sc)}
    order = sorted(by, key=lambda t: -by[t][1]['total'])
    rk = {t: i + 1 for i, t in enumerate(order)}
    nfset = {c['ticker'] for c in json.load(open(R + f'{folder}/{nf}'))} if nf else {t for t in by if (nd.get(t) or {}).get('tier') != 'F'}
    dl = {k for k in L(R + f'{folder}/delisted.json', {}) if not k.startswith('_')}
    ds = {k for k in L(R + f'{folder}/distress_flags.json', {}) if not k.startswith('_')}
    st = dict(pool=len(by), nonfin=len(nfset), excluded=0, hist=0, nocfo=0, nogm=0, passed=0, strict=0)
    out = []
    for t, (c, s) in by.items():
        if t not in nfset:
            continue
        if t in dl or t in ds:
            st['excluded'] += 1
            continue
        h = [v for v in c['revHist'] if v is not None]
        if len(h) < 9 or h[0] <= 0:
            continue
        st['hist'] += 1
        if c['cfoPct'] is None:
            st['nocfo'] += 1
            continue
        cagr = (h[-1] / h[0]) ** (1 / (len(h) - 1)) - 1
        ups = sum(1 for a, b in zip(h, h[1:]) if b > a) / (len(h) - 1)
        base = ups >= 0.7 and cagr >= 0.06 and c['profitPct'] >= 0.8 and c['cfoPct'] >= 0.8 and (c['dilution'] or 0) <= 0.1
        if base and not s['gm']:
            st['nogm'] += 1
        if base and (s['gm'] or 0) >= 0.30:
            worst = min(b / a - 1 for a, b in zip(h, h[1:]))
            e = nd.get(t) or {}
            out.append(dict(c=c, t=t, cagr=cagr, ups=ups, worst=worst, s=s, rank=rk[t], hist=h, g1=h[-1] / h[-2] - 1,
                            nd=e.get('netDebtUsd') if e.get('tier') in ('A', 'B') else None, ndfl=e.get('flags') or [],
                            strict=bool(cagr >= 0.08 and worst > -0.10)))
    st['passed'] = len(out)
    st['strict'] = sum(r['strict'] for r in out)
    return out, st


HEAD = ['v6 rank', 'Company', 'Ticker', 'Country', 'Revenue 9 yrs ago ($m)', 'Revenue LTM ($m)', 'Revenue growth per year',
        '% of periods revenue up', 'Worst single-period change', 'Last-period revenue growth', 'Gross margin', 'Profitable periods',
        'CFO+ periods', 'Dividend periods', 'Dilution', 'Market cap ($m)', 'Avg net income, last 4 periods ($m)', 'P/E (on avg NI)',
        'Net debt ($m)', 'Net debt / market cap', 'Screen notes', 'Business', 'Competitive position', 'Main shareholders',
        'Insider ownership', 'Red flags', 'Website', 'Passes earlier strict screen (8%+ a year, no drop worse than -10%)']
WIDTH = [8, 30, 15, 12, 11, 11, 10, 10, 11, 11, 9, 10, 9, 10, 9, 11, 13, 9, 11, 11, 38, 60, 70, 50, 40, 36, 28, 16]
hdr_fill = PatternFill('solid', fgColor='2F4B3C')
thin = Side(style='thin', color='D5DDD8')


def notes_for(r):
    n = []
    if r['worst'] <= -0.30:
        n.append(f"one-off revenue drop of {r['worst']:.0%} in a single period")
    elif r['worst'] <= -0.10:
        n.append(f"worst single-period revenue drop {r['worst']:.0%}")
    if r['g1'] < 0:
        n.append(f"revenue fell {r['g1']:.0%} in the latest period")
    mc = r['s']['mc']
    if r['nd'] is not None and mc and r['nd'] > 0.8 * mc:
        n.append(f"net debt {r['nd'] / mc:.1f}x market cap")
    if r['nd'] is not None and mc and r['nd'] < -0.8 * mc:
        n.append('net cash above 80% of market cap (cash may be restricted or client money)')
    if r['nd'] is None:
        n.append('no net-debt data')
    for f in r['ndfl']:
        if 'minority' in f:
            n.append('large minority interests')
    return '; '.join(n)


NOTE2 = 'Revenue history is in US dollars at historical exchange rates (Capital IQ), so growth for non-dollar currencies is understated or overstated against local-currency growth. Market caps are the live dashboard values.'


def sheet(ws, items, title):
    ws.append([title])
    ws['A1'].font = Font(name=F, bold=True, size=12)
    ws.append([NOTE2])
    ws['A2'].font = Font(name=F, italic=True, size=9, color='5B6B62')
    ws.append(HEAD)
    for i, h in enumerate(HEAD, 1):
        c = ws.cell(row=3, column=i)
        c.font = Font(name=F, bold=True, color='FFFFFF', size=10)
        c.fill = hdr_fill
        c.alignment = Alignment(wrap_text=True, vertical='center', horizontal='center')
    ws.row_dimensions[3].height = 56
    for k, r in enumerate(sorted(items, key=lambda r: r['rank'])):
        row = 4 + k
        c, s = r['c'], r['s']
        th = c.get('thesis') if isinstance(c.get('thesis'), dict) else {}
        link = th.get('website') or ''
        avg = c['avgNI']
        vals = [r['rank'], c['name'], r['t'], c['country'], r['hist'][0], r['hist'][-1], f'=(F{row}/E{row})^(1/9)-1', r['ups'], r['worst'], r['g1'],
                s['gm'], c['profitPct'], c['cfoPct'], c['divPct'], c['dilution'], round(s['mc'], 1), None if avg is None else round(avg, 2),
                f'=IF(AND(ISNUMBER(Q{row}),Q{row}>0),P{row}/Q{row},"n/m")', None if r['nd'] is None else round(r['nd'], 1),
                f'=IF(ISNUMBER(S{row}),S{row}/P{row},"")', notes_for(r),
                th.get('business_description') or 'No thesis in the dashboard yet.', th.get('competitive_position') or '',
                th.get('main_shareholders') or '', th.get('insider_ownership') or '', th.get('red_flags') or '', link,
                'Yes' if r['strict'] else 'No']
        for i, v in enumerate(vals, 1):
            cell = ws.cell(row=row, column=i, value=clean(v))
            cell.font = Font(name=F, size=9, color='0000FF' if (i in (5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 19) and not isinstance(v, str)) else '000000')
            cell.alignment = Alignment(wrap_text=i >= 21, vertical='top', horizontal='left' if i in (2, 3, 4) or i >= 21 else 'right')
            cell.border = Border(bottom=thin)
        ws.cell(row=row, column=28).alignment = Alignment(horizontal='center', vertical='top')
        for i, fmt in ((5, '#,##0.0'), (6, '#,##0.0'), (7, '0.0%'), (8, '0%'), (9, '0%;[Red]-0%'), (10, '0%;[Red]-0%'), (11, '0%'), (12, '0%'), (13, '0%'), (14, '0%'),
                       (15, '0.0%;-0.0%'), (16, '#,##0'), (17, '#,##0.0'), (18, '0.0"x"'), (19, '#,##0;-#,##0'), (20, '0.00;-0.00')):
            ws.cell(row=row, column=i).number_format = fmt
        ws.row_dimensions[row].height = 150
        if link:
            ws.cell(row=row, column=27).hyperlink = link
            ws.cell(row=row, column=27).font = Font(name=F, size=9, color='0563C1', underline='single')
    for i, w in enumerate(WIDTH, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = 'D4'
    ws.auto_filter.ref = f'A3:{get_column_letter(len(HEAD))}{3 + len(items)}'


res = {}
for reg in REGIONS:
    res[reg[0]] = screen(*reg)

wb = Workbook()
ov = wb.active
ov.title = 'Overview'
# Asia tabs first (as delivered), then the other regions
asia_items, asia_st = res['Asia & Pacific']
asia_new = [r for r in asia_items if not r['strict']]
asia_old = [r for r in asia_items if r['strict']]
tabs = [('Asia - 34 new names', asia_new, f'Asia & Pacific: {len(asia_new)} companies added when the single-drop limit was removed and growth lowered to 6% a year'),
        ('Asia - 32 earlier names', asia_old, f'Asia & Pacific: {len(asia_old)} companies that passed the earlier screen (growth >= 8% a year, no single-period drop worse than -10%)')]
for label in ('Europe', 'USA & Canada', 'Europe micro'):
    items, st = res[label]
    tabs.append((f'{label} ({len(items)})', items, f'{label}: {len(items)} companies passing the screen ({st["strict"]} of them also pass the earlier, stricter screen - see the last column)'))
for name, items, title in tabs:
    sheet(wb.create_sheet(name), items, title)

# ---- overview sheet
ov.append(['Revenue compounders - non-financial companies with steady revenue growth, by region'])
ov['A1'].font = Font(name=F, bold=True, size=13)
ov.append(['Screen: revenue growth >= 6% a year, revenue up in >= 70% of periods, profitable and cash-flow positive in >= 80% of periods, gross margin >= 30%, dilution <= 10%. No limit on single-period drops.'])
ov['A2'].font = Font(name=F, italic=True, size=9, color='5B6B62')
hdr = ['Region', 'Companies in pool', 'Non-financial', 'Delisted / distress flagged', 'With 9+ periods of revenue and cash-flow data', 'Pass the screen', 'Also pass the earlier strict screen', 'Pass the growth tests but have no gross margin (cannot be screened)', 'Share of screened that pass']
ov.append([])
ov.append(hdr)
for i, h in enumerate(hdr, 1):
    c = ov.cell(row=4, column=i)
    c.font = Font(name=F, bold=True, color='FFFFFF', size=10)
    c.fill = hdr_fill
    c.alignment = Alignment(wrap_text=True, vertical='center', horizontal='center')
ov.row_dimensions[4].height = 58
for k, label in enumerate(['Asia & Pacific', 'Europe', 'USA & Canada', 'Europe micro']):
    st = res[label][1]
    row = 5 + k
    vals = [label, st['pool'], st['nonfin'], st['excluded'], st['hist'] - st['nocfo'], st['passed'], st['strict'], st['nogm'], f'=F{row}/E{row}']
    for i, v in enumerate(vals, 1):
        cell = ov.cell(row=row, column=i, value=v)
        cell.font = Font(name=F, size=10, color='0000FF' if isinstance(v, int) else '000000')
        cell.alignment = Alignment(horizontal='left' if i == 1 else 'right')
        cell.border = Border(bottom=thin)
    ov.cell(row=row, column=9).number_format = '0.0%'
row = 9
ov.cell(row=row, column=1, value='Total').font = Font(name=F, bold=True, size=10)
for i in range(2, 9):
    col = get_column_letter(i)
    c = ov.cell(row=row, column=i, value=f'=SUM({col}5:{col}8)')
    c.font = Font(name=F, bold=True, size=10)
    c.alignment = Alignment(horizontal='right')
ov.cell(row=row, column=9, value='=F9/E9').number_format = '0.0%'
ov.cell(row=row, column=9).font = Font(name=F, bold=True, size=10)
ov.cell(row=row, column=9).alignment = Alignment(horizontal='right')
notes = [
    'Reading the overview',
    '- "Pass the screen" lists are on the other tabs, sorted by v6 rank, with thesis commentary (business, competitive position, shareholders, red flags) from the dashboard research notes.',
    '- Europe uses tier F in the net-debt file to mark financial companies (banks, insurers); the other pools have a separate non-financial file.',
    '- Companies without a gross margin cannot pass the margin test; the column "have no gross margin" shows how many would otherwise have passed (the overview column shows the count per region).',
    '- Colour code in the data tabs: blue = values taken from the dashboard data, black = formulas (revenue growth per year, P/E, net debt / market cap) and text.',
    '- P/E uses the average of the last four trailing-12-month net income figures. Net debt is shown only where the Yahoo / research data exist.',
    '- Revenue history is in US dollars at historical exchange rates. This is a screen, not a recommendation.',
]
for k, t in enumerate(notes):
    c = ov.cell(row=11 + k, column=1, value=t)
    c.font = Font(name=F, bold=(k == 0), size=10)
    c.alignment = Alignment(wrap_text=False)
for i, w in enumerate([18, 14, 14, 16, 16, 14, 18, 30, 14], 1):
    ov.column_dimensions[get_column_letter(i)].width = w

out = R + 'docs/revenue-compounders.xlsx'
wb.save(out)
for label, (items, st) in res.items():
    print(label, st)
print('saved', out)
