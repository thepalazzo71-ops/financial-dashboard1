"""PDF: companies that gained score/rank from the Yahoo dividend fill, per region.  Output: docs/dividend-fill-gainers.pdf

'Before' = pools as committed just before the Yahoo dividend merge (git commit given by BEFORE_REV); 'now' = current pools.
"""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts' / 'research'))
import scoring as S  # noqa: E402
import movers_report as MR  # noqa: E402  (fonts, styles, helpers)
from reportlab.graphics.shapes import Drawing, Line, Rect, String  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.platypus import BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle  # noqa: E402

ST, esc, short, usd = MR.ST, MR.esc, MR.short, MR.usd
colors = MR.colors
INK, SOFT, RULE, BRAND, UP, DOWN, PAPER, UPBG = MR.INK, MR.SOFT, MR.RULE, MR.BRAND, MR.UP, MR.DOWN, MR.PAPER, MR.UPBG

BEFORE_REV = '2c0a0a6~1'      # commit before "Fill missing dividend data from Yahoo Finance"
REGIONS = [('Europe', 'data', 'companies_1000_scored.json'), ('USA & Canada', 'data-us', 'companies_pool_all.json'),
           ('Asia & Pacific', 'data-asia', 'companies_pool_all.json'), ('Europe micro', 'data-micro', 'companies_pool_all.json')]
TOP_DETAIL = {'Europe': 29, 'USA & Canada': 24, 'Asia & Pacific': 40, 'Europe micro': 12}


def rank(pool, ov, gmo, dl):
    sc, _ = S.score_pool(pool, ov, gmo)
    rows = [(c, s) for c, s in zip(pool, sc) if c['ticker'] not in dl]
    rows.sort(key=lambda x: -x[1]['total'])
    return {c['ticker']: (i + 1, s['total'], c['fixedPts']['dividend_consistency'], c) for i, (c, s) in enumerate(rows)}


def analyse():
    out = {}
    for label, folder, pf in REGIONS:
        old = json.loads(subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{BEFORE_REV}:{folder}/{pf}']))
        new = json.load(open(ROOT / folder / pf))
        ov = json.load(open(ROOT / folder / 'mc_overrides_applied.json'))
        gmo = S.load_overrides()[1] if folder == 'data' else {}
        try:
            dl = {k for k in json.load(open(ROOT / folder / 'delisted.json')) if not k.startswith('_')}
        except Exception:
            dl = set()
        yd = json.load(open(ROOT / folder / 'dividends_yahoo.json'))
        a, b = rank(old, ov, gmo, dl), rank(new, ov, gmo, dl)
        rows = []
        for t, (r1, s1, dp1, c0) in a.items():
            r2, s2, dp2, c = b[t]
            if s2 - s1 <= 0.01:
                continue
            n = c.get('nRevPeriods') or 10
            fl = c.get('divFlags') or []
            h = c.get('divHist') or []
            amt = next((v for v in reversed(h) if v is not None), None)
            amt_is_ltm = bool(h) and h[-1] is not None
            l4 = [v for v in h[-4:] if v is not None]
            payout = None
            if l4 and c.get('avgNI') and c['avgNI'] > 0:
                payout = (sum(l4) / len(l4)) / c['avgNI']
            y = yd.get(t) or {}
            note = []
            if fl and fl[-1] == 0 and sum(fl) > 0:
                note.append('latest period shown unpaid')
            if sum(fl[-n:]) <= 3:
                note.append(f'only {sum(fl[-n:])} paid period(s)')
            if c.get('is_financial_sector'):
                note.append('financial')
            rows.append(dict(t=t, n=c['name'], co=c['country'], r1=r1, r2=r2, move=r1 - r2, s1=s1, s2=s2, dp1=dp1, dp2=dp2,
                             paid=sum(fl[-n:]), nper=n, amt=amt, ltm=amt_is_ltm, payout=payout, last=y.get('lastEvent'), sym=y.get('sym'),
                             amounts=h, flags=fl, note='; '.join(note), mc=b[t][3].get('mc0')))
        rows.sort(key=lambda x: (-x['move'], x['r2']))
        t50a = {t for t, v in a.items() if v[0] <= 50}
        t50b = {t for t, v in b.items() if v[0] <= 50}
        mv = sorted(abs(a[t][0] - b[t][0]) for t in a)
        out[label] = dict(n=len(a), rows=rows, in50=[b[t] for t in t50b - t50a], out50=[a[t] for t in t50a - t50b],
                          a=a, b=b, median_move=mv[len(mv) // 2], over50=sum(1 for v in mv if v > 50),
                          avg_gain=sum(r['s2'] - r['s1'] for r in rows) / max(len(rows), 1))
    return out


def gain_chart(items, width):
    rh, name_w = 11.5, 165
    height = rh * len(items) + 12
    d = Drawing(width, height)
    mx = max(x['move'] for x in items) or 1
    half = width - name_w - 40
    for i, x in enumerate(items):
        y = height - 8 - (i + 1) * rh + 2
        d.add(String(name_w - 4, y + 1.5, short(x['n'], 32), fontName='LS', fontSize=7, fillColor=INK, textAnchor='end'))
        w = x['move'] / mx * half
        d.add(Rect(name_w, y, w, rh - 3.5, fillColor=UP, strokeColor=None))
        d.add(String(name_w + w + 3, y + 1.5, f'+{x["move"]}  ({x["r1"]} → {x["r2"]})', fontName='LS-B', fontSize=6.8, fillColor=UP))
    d.add(Line(name_w, 4, name_w, height - 6, strokeColor=RULE, strokeWidth=0.8))
    return d


def hdr(cols):
    return [Paragraph(c, ST['hdr']) for c in cols]


def detail_table(items, W):
    head = ['Company', 'Rank\nbefore → now', 'Score\nbefore → now', 'Dividend\npoints', 'Periods\npaid', 'Latest dividend', 'Notes']
    data = [hdr([h.replace('\n', '<br/>') for h in head])]
    for x in items:
        pay = f' · payout {x["payout"]:.0%} of NI' if x['payout'] else ''
        if x['amt'] is None:
            latest = 'paid – amount n/a' if (x['flags'] and x['flags'][-1]) else ('none in latest period' if x['paid'] else 'none')
        else:
            latest = f'{usd(x["amt"], 1)} ({"LTM" if x["ltm"] else "latest reported"}){pay}'
        if x['last']:
            latest += f'<br/><font color="#5B6B62">last payment {x["last"]}</font>'
        data.append([
            Paragraph(f'<b>{esc(short(x["n"], 30))}</b><br/><font color="#5B6B62">{esc(x["co"])}</font>', ST['cell']),
            Paragraph(f'{x["r1"]:,} → <b>{x["r2"]:,}</b><br/><font color="#2F7D4F"><b>{"+" if x["move"] > 0 else "−" if x["move"] < 0 else "±"}{abs(x["move"]):,}</b></font>', ST['cell']),
            Paragraph(f'{x["s1"]:.1f} → <b>{x["s2"]:.1f}</b>', ST['cell']),
            Paragraph(f'{x["dp1"]:.1f} → <b>{x["dp2"]:.1f}</b>', ST['cell']),
            Paragraph(f'{x["paid"]} of {x["nper"]}', ST['cell']),
            Paragraph(latest, ST['cell']),
            Paragraph(f'<font color="#B4432F">{esc(x["note"])}</font>' if x['note'] else '', ST['cell']),
        ])
    t = Table(data, colWidths=[W * 0.215, W * 0.115, W * 0.115, W * 0.095, W * 0.075, W * 0.25, W * 0.135], repeatRows=1)
    style = [('BACKGROUND', (0, 0), (-1, 0), BRAND), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 1), (-1, -1), 0.4, RULE),
             ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2), ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4)]
    for r in range(2, len(data), 2):
        style.append(('BACKGROUND', (0, r), (-1, r), UPBG))
    t.setStyle(TableStyle(style))
    return t


def compact_table(items, W):
    cs = MR.ParagraphStyle('cc', parent=ST['cell'], fontSize=6.6, leading=7.8)
    data = [hdr(['Company', 'Country', 'Rank before → now', 'Score', 'Div. pts', 'Paid', 'Latest $m'])]
    for x in items:
        data.append([Paragraph(esc(short(x['n'], 38)), cs), Paragraph(esc(x['co']), cs),
                     Paragraph(f'{x["r1"]:,} → {x["r2"]:,} ({"+" if x["move"] > 0 else "−" if x["move"] < 0 else "±"}{abs(x["move"]):,})', cs),
                     Paragraph(f'{x["s1"]:.1f} → {x["s2"]:.1f}', cs), Paragraph(f'{x["dp1"]:.1f} → {x["dp2"]:.1f}', cs),
                     Paragraph(f'{x["paid"]}/{x["nper"]}', cs), Paragraph('–' if x['amt'] is None else f'{x["amt"]:,.1f}', cs)])
    t = Table(data, colWidths=[W * 0.31, W * 0.13, W * 0.20, W * 0.12, W * 0.1, W * 0.06, W * 0.08], repeatRows=1)
    style = [('BACKGROUND', (0, 0), (-1, 0), BRAND), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LINEBELOW', (0, 1), (-1, -1), 0.3, RULE),
             ('TOPPADDING', (0, 0), (-1, -1), 1.2), ('BOTTOMPADDING', (0, 0), (-1, -1), 1.2), ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3)]
    for r in range(2, len(data), 2):
        style.append(('BACKGROUND', (0, r), (-1, r), PAPER))
    t.setStyle(TableStyle(style))
    return t


def build(path):
    res = analyse()

    def deco(canvas, doc):
        canvas.saveState()
        canvas.setFont('LS', 7.2)
        canvas.setFillColor(SOFT)
        canvas.drawString(18 * mm, 10 * mm, 'Value-stock dashboards – companies that gained from the Yahoo dividend fill')
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f'Page {doc.page}')
        canvas.setStrokeColor(RULE)
        canvas.line(18 * mm, 13.5 * mm, A4[0] - 18 * mm, 13.5 * mm)
        canvas.restoreState()

    doc = BaseDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                          title='Companies that gained from the Yahoo dividend fill', author='Claude Code')
    doc.addPageTemplates([PageTemplate(id='p', frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=deco)])
    W = doc.width
    S_ = []
    S_.append(Paragraph('Who gained from the Yahoo dividend fill', ST['title']))
    S_.append(Paragraph(f'Companies whose score and rank rose after missing dividend history was filled from Yahoo Finance · {date.today():%d %B %Y}', ST['sub']))
    S_.append(Paragraph(
        '<b>What happened.</b> The Capital IQ extract had no dividend history for 678 companies, so they scored 0 of 4 dividend-consistency points even when they pay dividends. '
        'Yahoo Finance had a dividend record for 635 of them. The score counts the periods (of up to 10 annual periods) in which a dividend was paid: '
        '<b>points = 4 × paid periods ÷ periods reported</b>. A company that paid in every period therefore gains the full 4 points, which lifts its total score by up to 4 points. '
        'Companies that already had Capital IQ dividend data are unchanged, so those that were filled can overtake them.', ST['body']))
    tab = [hdr(['', 'Companies in pool', 'Gained points', 'Avg gain', 'Moved > 50 places', 'Top 50: in / out'])]
    for label, v in res.items():
        tab.append([Paragraph(f'<b>{label}</b>', ST['cell']), Paragraph(f'{v["n"]:,}', ST['cell']), Paragraph(f'{len(v["rows"]):,}', ST['cell']),
                    Paragraph(f'+{v["avg_gain"]:.2f} pts', ST['cell']), Paragraph(f'{v["over50"]:,}', ST['cell']),
                    Paragraph(f'{len(v["in50"])} / {len(v["out50"])}', ST['cell'])])
    t = Table(tab, colWidths=[W * 0.2, W * 0.17, W * 0.15, W * 0.14, W * 0.18, W * 0.16], repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), BRAND), ('LINEBELOW', (0, 1), (-1, -1), 0.4, RULE), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                           ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    S_ += [Spacer(1, 4), t, Spacer(1, 8)]
    S_.append(Paragraph('How big were the rank changes?', ST['h2']))
    for b in [
        '<b>At the top of each ranking, small.</b> Europe’s top 100 did not change at all; the US, Asia and micro top 50s each swapped one company.',
        '<b>In the middle of Asia’s ranking, large.</b> 567 Asian companies (30% of the pool) gained about 4 points each where scores are packed tightly, so companies jumped by up to 300 places. '
        'Companies that did not gain were pushed down in return, by up to 143 places.',
        '<b>The Asian ranking is now more even-handed.</b> Dividend payers with no Capital IQ history used to be marked down against companies whose dividends were recorded.',
    ]:
        S_.append(Paragraph(b, ST['bullet'], bulletText='•'))
    S_.append(Paragraph('Reading the tables', ST['h2']))
    S_.append(Paragraph(
        '“Rank before → now” and “Score before → now” compare the ranking just before and just after the merge (valuation, price and every other input held constant). '
        '“Periods paid” counts the annual periods, of the 10 in the history, in which a dividend payment fell. “Latest dividend” is the cash paid in the latest period '
        'where Yahoo reports it (US-dollar millions at today’s exchange rates); “LTM” means the latest fiscal year, “latest reported” an earlier one because Yahoo lacks the newest. '
        'Payout is the average of the last four dividend figures divided by the 4-period average net income.', ST['small']))
    S_.append(Paragraph('Caveats', ST['h2']))
    for b in [
        'Yahoo’s paid / not-paid flags are approximate: a payment date drifting across a 12-month boundary can leave one period unpaid (“latest period shown unpaid” in the notes), which costs up to 0.4 points.',
        'Amounts exist only for roughly the last 4 fiscal years; earlier periods show whether a dividend was paid, not how much.',
        'Companies with only a few paid periods gain fewer points; they are noted in the tables.',
        '43 of the 678 companies had no dividend record in Yahoo either (mostly Romanian and OTC listings); they still show no dividend data and are not in this report.',
    ]:
        S_.append(Paragraph(b, ST['bullet'], bulletText='•'))
    S_.append(PageBreak())

    for label, v in res.items():
        rows = v['rows']
        S_.append(Paragraph(label, ST['h1']))
        S_.append(Paragraph(f'{len(rows):,} companies gained (average +{v["avg_gain"]:.2f} points) · {v["over50"]:,} of {v["n"]:,} companies moved more than 50 places · median move {v["median_move"]} places', ST['sub']))
        if v['in50'] or v['out50']:
            ins = '; '.join(f'<b>{esc(short(x[3]["name"], 28))}</b> ({v["a"][x[3]["ticker"]][0]} → {x[0]})' for x in sorted(v['in50'], key=lambda x: x[0]))
            outs = '; '.join(f'{esc(short(x[3]["name"], 28))} ({x[0]} → {v["b"][x[3]["ticker"]][0]})' for x in sorted(v['out50'], key=lambda x: x[0]))
            S_.append(Paragraph(f'<b>Entered the top 50:</b> {ins or "none"}.&nbsp; <b>Left the top 50:</b> {outs or "none"}.', ST['body']))
        else:
            S_.append(Paragraph('<b>Top 50:</b> no change.', ST['body']))
        shown = rows[:TOP_DETAIL[label]]
        if len(rows) > 12:
            S_.append(Paragraph(f'Largest rank gains', ST['h2']))
            S_.append(gain_chart(rows[:15], W))
            S_.append(Spacer(1, 6))
        S_.append(Paragraph(f'{"All" if len(shown) == len(rows) else "Top " + str(len(shown))} companies that gained, by rank improvement', ST['h2']))
        S_.append(detail_table(shown, W))
        if len(rows) > len(shown):
            S_.append(PageBreak())
            S_.append(Paragraph(f'{label} – all {len(rows):,} companies that gained (compact list, by rank improvement)', ST['h2']))
            S_.append(compact_table(rows, W))
        S_.append(PageBreak())
    S_.pop()
    doc.build(S_)
    print('wrote', path)


if __name__ == '__main__':
    build(ROOT / 'docs' / 'dividend-fill-gainers.pdf')
