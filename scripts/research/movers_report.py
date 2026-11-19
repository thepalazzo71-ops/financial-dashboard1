"""PDF: which companies moved most in the ranking (up and down) per region when the valuation lenses switched from
market cap to EV (net cash capped at 50% of market cap, ~3-year average earnings).  Output: docs/valuation-ev-movers.pdf
"""
import math
import sys
from datetime import date
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'research'))
import movers_data as MD  # noqa: E402

FD = '/usr/share/fonts/truetype/liberation/'
pdfmetrics.registerFont(TTFont('LS', FD + 'LiberationSans-Regular.ttf'))
pdfmetrics.registerFont(TTFont('LS-B', FD + 'LiberationSans-Bold.ttf'))
pdfmetrics.registerFont(TTFont('LS-I', FD + 'LiberationSans-Italic.ttf'))
pdfmetrics.registerFont(TTFont('LS-BI', FD + 'LiberationSans-BoldItalic.ttf'))
pdfmetrics.registerFontFamily('LS', normal='LS', bold='LS-B', italic='LS-I', boldItalic='LS-BI')

INK, SOFT, RULE = colors.HexColor('#1F2A24'), colors.HexColor('#5B6B62'), colors.HexColor('#D5DDD8')
BRAND, UP, DOWN = colors.HexColor('#2F4B3C'), colors.HexColor('#2F7D4F'), colors.HexColor('#B4432F')
PAPER, UPBG, DOWNBG = colors.HexColor('#F4F6F4'), colors.HexColor('#E5F1E9'), colors.HexColor('#F8E7E2')

ST = dict(
    title=ParagraphStyle('t', fontName='LS-B', fontSize=24, leading=28, textColor=BRAND, spaceAfter=4),
    sub=ParagraphStyle('s', fontName='LS', fontSize=11, leading=15, textColor=SOFT, spaceAfter=10),
    h1=ParagraphStyle('h1', fontName='LS-B', fontSize=16, leading=20, textColor=BRAND, spaceBefore=4, spaceAfter=6),
    h2=ParagraphStyle('h2', fontName='LS-B', fontSize=11.5, leading=15, textColor=INK, spaceBefore=8, spaceAfter=4),
    body=ParagraphStyle('b', fontName='LS', fontSize=9.2, leading=13, textColor=INK, spaceAfter=5, alignment=TA_LEFT),
    small=ParagraphStyle('sm', fontName='LS', fontSize=7.6, leading=10, textColor=SOFT),
    cell=ParagraphStyle('c', fontName='LS', fontSize=7.1, leading=8.6, textColor=INK),
    cellb=ParagraphStyle('cb', fontName='LS-B', fontSize=7.1, leading=8.6, textColor=INK),
    hdr=ParagraphStyle('h', fontName='LS-B', fontSize=7.2, leading=9, textColor=colors.white),
    bullet=ParagraphStyle('bl', fontName='LS', fontSize=9.2, leading=13, textColor=INK, leftIndent=11, bulletIndent=0, spaceAfter=3),
)


def esc(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def short(n, k=34):
    n = n.replace(' Aktiengesellschaft', ' AG').replace(' Societe Anonyme', ' SA').replace(' Spolka Akcyjna', ' SA')
    return n if len(n) <= k else n[:k - 1].rstrip() + '…'


def usd(v, d=0):
    if v is None:
        return '–'
    return ('−' if v < 0 else '') + f'${abs(v):,.{d}f}m'


def m(v, d=0):
    if v is None:
        return '–'
    s = f'{abs(v):,.{d}f}'
    return ('−' if v < 0 else '') + s


# --------------------------------------------------------------------------------------------- driver text
def spike(x, hist):
    h = [v for v in hist if v is not None]
    if len(h) >= 4 and x['ni3'] and abs(x['ni3']) > 0:
        return max(abs(v) for v in h) / abs(x['ni3']) > 4 and abs(x['ni3']) > 1
    return False


def ni_dir(x):
    """+1 if the 3-yr average is materially higher than last year's average, -1 if lower, 0 otherwise."""
    ni1, ni3 = x['ni1'], x['ni3']
    if ni1 is None or ni3 is None:
        return 0
    if ni1 <= 0 < ni3:
        return 1
    if ni3 <= 0 < ni1:
        return -1
    if ni1 > 0 and ni3 > 0 and abs(math.log(ni3 / ni1)) > 0.25:
        return 1 if ni3 > ni1 else -1
    return 0


def drivers(x):
    """-> (headline, detail) strings describing why the company moved."""
    parts, tags = [], []
    ev_log = abs(math.log(x['evmc'])) if x['evmc'] and x['has_nd'] else 0
    ni1, ni3 = x['ni1'], x['ni3']
    if ni1 is not None and ni3 is not None:
        if ni1 <= 0 < ni3:
            ni_log = 1.6
        elif ni3 <= 0 < ni1:
            ni_log = 1.6
        elif ni1 > 0 and ni3 > 0:
            ni_log = abs(math.log(ni3 / ni1))
        else:
            ni_log = 0.3
    else:
        ni_log = 0
    if x['has_nd']:
        if x['capped']:
            parts.append(f"net cash ({usd(abs(x['nd']))}) exceeds half the market cap → EV capped at 0.50× market cap")
            tags.append('Net cash')
        elif x['nd'] < 0 and ev_log > 0.1:
            parts.append(f"net cash {usd(abs(x['nd']))} → EV {x['evmc']:.2f}× market cap")
            tags.append('Net cash')
        elif x['nd'] > 0 and ev_log > 0.1:
            parts.append(f"net debt {usd(x['nd'])} → EV {x['evmc']:.2f}× market cap")
            tags.append('Net debt')
    else:
        parts.append('no net-debt record (EV = market cap)' + (' – financial' if x['fin'] else ''))
    if ni_log > 0.25:
        if ni1 is not None and ni1 <= 0 < ni3:
            parts.append(f"3-yr avg profit {usd(ni3, 1)} vs last-yr avg loss of {usd(abs(ni1), 1)}")
        elif ni3 is not None and ni3 <= 0 < (ni1 or 0):
            parts.append(f"3-yr avg negative ({usd(ni3, 1)}) vs last-yr avg profit {usd(ni1, 1)}")
        else:
            parts.append(f"3-yr avg profit {usd(ni3, 1)} vs {usd(ni1, 1)} last yr ({ni3 / ni1:.1f}×)")
        tags.append('Earnings')
    if not tags:
        tags.append('Pool ripple')
        r = f" and the 3-yr average is {x['ni3'] / x['ni1']:.1f}× last year’s" if x['ni1'] and x['ni3'] and x['ni1'] > 0 else ''
        parts.append(f"small input changes (EV {x['evmc']:.2f}× market cap{r}), amplified because scores are tightly bunched at this rank")
    return ' + '.join(tags), '; '.join(parts)


def cautions(x, hist):
    c = []
    if spike(x, hist):
        c.append('3-yr average dominated by one period')
    if x['distress']:
        c.append(f"{x['distress']} distress flag")
    for f in x['nd_flags']:
        if 'older than' in f:
            c.append('balance sheet older than Q1 2026')
        elif 'minority' in f:
            c.append('large minority interests')
        elif '3x market cap' in f:
            c.append(f.split('(')[0].strip())
    if x['mc'] is not None and x['mc'] < 20 and x['ni3'] is not None and abs(x['ni3']) < 0.5 and x['move'] > 0:
        c.append('tiny earnings figures (<$0.5m)')
    return c


# --------------------------------------------------------------------------------------------- chart
def bar_chart(ups, downs, width=500):
    rows = [(x, x['move']) for x in ups] + [(x, x['move']) for x in downs]
    rh, name_w, pad = 11.5, 150, 28
    height = rh * len(rows) + 22
    d = Drawing(width, height)
    mx = max(abs(v) for _, v in rows)
    x0 = name_w + (width - name_w) / 2
    half = (width - name_w) / 2 - pad
    d.add(Line(x0, 8, x0, height - 14, strokeColor=RULE, strokeWidth=0.8))
    d.add(String(x0 + 4, height - 11, 'rose  (ranks gained)', fontName='LS-B', fontSize=7, fillColor=UP))
    d.add(String(x0 - 4, height - 11, 'fell  (ranks lost)', fontName='LS-B', fontSize=7, fillColor=DOWN, textAnchor='end'))
    for i, (x, v) in enumerate(rows):
        y = height - 22 - (i + 1) * rh + 2
        d.add(String(name_w - 4, y + 1.5, short(x['n'], 30), fontName='LS', fontSize=7, fillColor=INK, textAnchor='end'))
        w = abs(v) / mx * half
        if v >= 0:
            d.add(Rect(x0, y, w, rh - 3.5, fillColor=UP, strokeColor=None))
            d.add(String(x0 + w + 3, y + 1.5, f'+{v:,}', fontName='LS-B', fontSize=6.8, fillColor=UP))
        else:
            d.add(Rect(x0 - w, y, w, rh - 3.5, fillColor=DOWN, strokeColor=None))
            d.add(String(x0 - w - 3, y + 1.5, f'{v:,}'.replace('-', '−'), fontName='LS-B', fontSize=6.8, fillColor=DOWN, textAnchor='end'))
    return d


# --------------------------------------------------------------------------------------------- tables
def mover_table(items, side, widths):
    head = ['Company', 'Rank (before → now)', 'Mkt cap $m', 'EV / MC', 'Driver', 'What changed']
    data = [[Paragraph(esc(h).replace('\n', '<br/>'), ST['hdr']) for h in head]]
    for x in items:
        tags, text = drivers(x)
        flags = cautions(x, x.get('niHist', []))
        what = esc(text[0].upper() + text[1:] + '.') if text else ''
        if flags:
            what += f' <font color="#B4432F"><b>Caution:</b> {esc("; ".join(flags))}.</font>'
        arrow_col = '#2F7D4F' if side == 'up' else '#B4432F'
        data.append([
            Paragraph(f'<b>{esc(short(x["n"], 30))}</b><br/><font color="#5B6B62">{esc(x["co"])}</font>', ST['cell']),
            Paragraph(f'{x["r_old"]:,} → <b>{x["r_new"]:,}</b><br/><font color="{arrow_col}"><b>{"+" if x["move"] > 0 else "−"}{abs(x["move"]):,}</b></font>', ST['cell']),
            Paragraph(m(x['mc']), ST['cell']),
            Paragraph(f'{x["evmc"]:.2f}×' + ('<br/><font color="#5B6B62">(n/a)</font>' if not x['has_nd'] else ''), ST['cell']),
            Paragraph(esc(tags), ST['cellb']),
            Paragraph(what, ST['cell']),
        ])
    t = Table(data, colWidths=widths, repeatRows=1)
    bg = UPBG if side == 'up' else DOWNBG
    style = [('BACKGROUND', (0, 0), (-1, 0), BRAND), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
             ('LINEBELOW', (0, 1), (-1, -1), 0.4, RULE), ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
             ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4)]
    for r in range(2, len(data), 2):
        style.append(('BACKGROUND', (0, r), (-1, r), bg))
    t.setStyle(TableStyle(style))
    return t


def stat_table(rows, widths):
    t = Table(rows, colWidths=widths)
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), PAPER), ('BOX', (0, 0), (-1, -1), 0.5, RULE),
                           ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    return t


def stat_cell(big, small):
    return Paragraph(f'<font name="LS-B" size="15" color="#2F4B3C">{big}</font><br/><font size="7.2" color="#5B6B62">{small}</font>', ST['cell'])


# --------------------------------------------------------------------------------------------- narrative
def region_story(label, v):
    ups, downs = v['up'], v['down']

    def cnt(items, pred):
        return sum(1 for x in items if pred(x))
    net_cash_up = cnt(ups, lambda x: x['has_nd'] and x['nd'] < 0 and x['evmc'] < 0.9)
    earn_up = cnt(ups, lambda x: ni_dir(x) > 0)
    nodebt_up = cnt(ups, lambda x: not x['has_nd'])
    debt_down = cnt(downs, lambda x: x['has_nd'] and x['nd'] > 0 and x['evmc'] > 1.15)
    earn_down = cnt(downs, lambda x: ni_dir(x) < 0)
    nodebt_down = cnt(downs, lambda x: not x['has_nd'])
    paras = [
        f"Of the {len(ups)} biggest risers, <b>{net_cash_up}</b> have net cash that pulls EV below market cap and <b>{earn_up}</b> gain mainly or partly "
        f"because their 3-year average profit is higher than last year’s ({nodebt_up} have no net-debt record, so for them the earnings basis is the only change). "
        f"Of the {len(downs)} biggest fallers, <b>{debt_down}</b> carry net debt that lifts EV well above market cap, <b>{earn_down}</b> are hit by a 3-year average below last year’s, and "
        f"<b>{nodebt_down}</b> have no net-debt record (their drop is the earnings basis or percentile ripple)."
    ]
    return paras


REGION_NOTES = {
    'Europe': [
        "Net cash companies dominate the climbers: OVB Holding, NRJ Group, High Co, Infas Holding and Celebrus all see EV fall to about half their market cap, which adds roughly 15–30 percentile points to their lens A score.",
        "EgnsINVEST Ejendomme (589 → 111) and Skarbiec Holding (469 → 242) have no net-debt record: they move purely because the 3-year average turns positive or rises, which lifts lens C.",
        "CTT – Correios de Portugal shows net cash of about $2.1bn against a ~$955m market cap, so the cap binds. That balance sheet almost certainly includes customer deposits of its bank subsidiary (Banco CTT) – treat this rise as unverified.",
        "Leveraged names fall: Speedy Hire, Graines Voltz and Surteco all carry EV near 3× market cap, which removes most of their lens A advantage.",
    ],
    'USA & Canada': [
        "Only 265 of 520 companies have net-debt data (most banks and insurers use market cap), so most of the pool changes only through the 3-year average.",
        "The sharpest falls are leveraged: E.W. Scripps (EV 11.6× market cap), TTEC (12.3×), Camping World (8.4×), American Vanguard (4.8×) and Willis Lease (3.2×). Lens A had carried them up the ranking; it stops working once debt is counted.",
        "UWM Holdings (457 → 169) is the largest US riser, but it is a data artefact: its net-income history includes a single $3.4bn period, so its 3-year average ($567m) is 32× the last-year average ($18m). See the watch-list page.",
        "Johnson Outdoors and Knight Therapeutics rise because large net cash lowers EV while the 3-year average smooths out a recent loss; Alpha Pro Tech combines net cash with a higher 3-year average.",
    ],
    'Asia & Pacific': [
        "Asia has the largest net-debt coverage (1,705 of 1,879) and the largest ranking churn: the median company moves 51 places, and 262 companies have their net cash capped at 50% of market cap.",
        "Nanyang Holdings (551 → 41) is the biggest rise in the whole project. It earns almost nothing today (last-year average −$0.6m) but has net cash of $98m and a 3-year average of $14.5m. Whether that deserves a top-50 rank is a judgement call – see the watch-list page.",
        "Korean and Japanese companies with very high net debt (Premium Group, Wonik QnC, Green Cross Holdings, Deutsch Motors, Pulmuone, Easy Holdings) drop 157–540 places once EV replaces market cap.",
        "Green Cross Holdings has $658m of minority interests: the net debt belongs partly to partly-owned subsidiaries, so the EV used here probably overstates the burden on shareholders.",
    ],
    'Europe micro': [
        "The micro pool is small (182) and moves are modest (median 5 places), but several of the largest climbers rest on tiny earnings figures: Provide IT Sweden, QubicGames and Kakel Max have 3-year average profits of $0.1–0.3m, enough to put them in the 77th–99th percentile on lens C.",
        "LUG (20 → 62), InTiCa Systems (65 → 105) and BigBen Interactive (6 → 34) fall because debt is now counted: LUG’s EV is 5.9× market cap and InTiCa’s 4.6×.",
        "BigBen’s rank also reflects a separate data correction: its fundamentals were replaced with the FY to March 2026 results (net loss €237m, equity −€21m) and it carries a severe-distress flag.",
    ],
}


def build(path):
    res = MD.analyse()
    # attach niHist for spike test
    import json
    for label, folder, poolf, _ in MD.REGIONS:
        pool = {c['ticker']: c for c in json.load(open(ROOT / folder / poolf))}
        for side in ('up', 'down'):
            for x in res[label][side]:
                x['niHist'] = pool[x['t']].get('niHist') or []

    def deco(canvas, doc):
        canvas.saveState()
        canvas.setFont('LS', 7.2)
        canvas.setFillColor(SOFT)
        canvas.drawString(18 * mm, 10 * mm, 'Value-stock dashboards – ranking movers after the switch to EV-based valuation')
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f'Page {doc.page}')
        canvas.setStrokeColor(RULE)
        canvas.line(18 * mm, 13.5 * mm, A4[0] - 18 * mm, 13.5 * mm)
        canvas.restoreState()

    doc = BaseDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                          title='Ranking movers after the switch to EV-based valuation', author='Claude Code')
    fr = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='f', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id='p', frames=[fr], onPage=deco)])
    W = doc.width
    S = []

    # ------------------------------------------------------------------ page 1: summary
    S.append(Paragraph('Who moved most in the ranking – and why', ST['title']))
    S.append(Paragraph(f'Biggest risers and fallers per region when the valuation score switched from market cap to enterprise value · {date.today():%d %B %Y}', ST['sub']))
    S.append(Paragraph(
        '<b>What changed.</b> Valuation is 18 of the ~100 score points. Until now two of its three tests used market cap; they now use '
        '<b>enterprise value (EV = market cap + net debt)</b>, with net cash credited only up to half the market cap, and the earnings test uses a '
        '<b>~3-year average</b> of profit instead of the last year’s. Companies with no net-debt record, and financials, keep market cap. '
        'Everything else in the score is unchanged, so every rank move below comes from the valuation points.', ST['body']))
    hdr = ['', 'Companies', 'With net debt', 'Top-50 unchanged', 'Rose / fell', 'Median move', 'Net cash capped']
    tab = [[Paragraph(h, ST['hdr']) for h in hdr]]
    for label in res:
        v = res[label]
        tab.append([Paragraph(f'<b>{label}</b>', ST['cell']), Paragraph(f'{v["n"]:,}', ST['cell']),
                    Paragraph(f'{v["nd_n"]:,} ({v["nd_n"] / v["n"]:.0%})', ST['cell']),
                    Paragraph(f'{v["overlap50"]} of 50', ST['cell']),
                    Paragraph(f'{v["rose_n"]:,} / {v["fell_n"]:,}', ST['cell']),
                    Paragraph(f'{v["median_abs"]} places', ST['cell']),
                    Paragraph(f'{v["capped_n"]}', ST['cell'])])
    t = Table(tab, colWidths=[W * 0.19, W * 0.11, W * 0.17, W * 0.15, W * 0.14, W * 0.13, W * 0.11], repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), BRAND), ('LINEBELOW', (0, 1), (-1, -1), 0.4, RULE), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                           ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    S += [Spacer(1, 4), t, Spacer(1, 8)]
    S.append(Paragraph('Three forces explain almost every large move', ST['h2']))
    for b in [
        '<b>Net cash lifts a company.</b> Cash on the balance sheet lowers EV, so revenue and earnings look cheaper relative to it. Among the biggest risers in Europe and Asia, net-cash companies are the largest group.',
        '<b>Net debt sinks a company.</b> A company whose EV is 2–12× its market cap loses most of its lens A and lens C advantage. This is the dominant reason behind the biggest falls in Europe, the US and Asia, and behind the largest falls in the micro pool.',
        '<b>The 3-year average changes the earnings basis.</b> A company whose last year was weak but earlier years were strong rises; one whose last year was its best falls. This is the only force acting on companies with no net-debt record (about half of the US pool).',
    ]:
        S.append(Paragraph(b, ST['bullet'], bulletText='•'))
    S.append(Paragraph('Read the risers with care', ST['h2']))
    S.append(Paragraph(
        'The new method is more demanding on the data, and several of the largest <i>rises</i> rest on inputs that deserve a second look: a single outsized year in the 3-year average '
        '(UWM Holdings), a company with no current profit but a positive 3-year average (Nanyang Holdings), net cash that probably includes customer deposits (CTT) and '
        'earnings of a few hundred thousand dollars in the micro pool. These are listed on the final page. The <i>falls</i> are generally better founded, because reported net debt is more '
        'robust than a profit average.', ST['body']))
    S.append(Paragraph(
        '<b>How the movers were chosen.</b> “Rank before” is the ranking with the old valuation tests, “rank now” the live ranking. Movers are the largest rank changes among companies that '
        'sit in the top 250 (top 100 in the micro pool) on either basis, so that moves at the bottom of the pool are not mistaken for signal. Delisted companies are excluded. '
        '“Main driver” is derived from the inputs: net cash / net debt when EV differs from market cap by more than about 10%, and earnings basis when the 3-year average differs from last year’s by more than about 28% or changes sign.', ST['small']))
    S.append(PageBreak())

    # ------------------------------------------------------------------ regions
    widths = [W * 0.20, W * 0.12, W * 0.075, W * 0.06, W * 0.105, W * 0.44]
    for label, v in res.items():
        S.append(Paragraph(label, ST['h1']))
        S.append(Paragraph(f'{v["n"]:,} companies ranked · net-debt data for {v["nd_n"]:,} · {v["overlap50"]} of the top 50 unchanged · '
                           f'{v["rose_n"]:,} companies rose, {v["fell_n"]:,} fell, median move {v["median_abs"]} places', ST['sub']))
        for para in region_story(label, v):
            S.append(Paragraph(para, ST['body']))
        S.append(bar_chart(v['up'], v['down'], W))
        S.append(Spacer(1, 4))
        for note in REGION_NOTES[label]:
            S.append(Paragraph(note, ST['bullet'], bulletText='•'))
        ent = [x for x in v['top50_new'] if x['r_old'] > 50]
        left = [x for x in v['top50_old'] if x['r_new'] > 50]
        S.append(Paragraph('Top-50 turnover', ST['h2']))
        S.append(Paragraph('<b>Entered the top 50:</b> ' + '; '.join(f'{esc(short(x["n"], 26))} ({x["r_old"]} → {x["r_new"]})' for x in sorted(ent, key=lambda x: x['r_new'])) + '.', ST['body']))
        S.append(Paragraph('<b>Left the top 50:</b> ' + '; '.join(f'{esc(short(x["n"], 26))} ({x["r_old"]} → {x["r_new"]})' for x in sorted(left, key=lambda x: x['r_old'])) + '.', ST['body']))
        S.append(PageBreak())
        S.append(Paragraph(f'{label} – biggest risers', ST['h2']))
        S.append(mover_table(v['up'], 'up', widths))
        S.append(Spacer(1, 10))
        S.append(Paragraph(f'{label} – biggest fallers', ST['h2']))
        S.append(mover_table(v['down'], 'down', widths))
        S.append(PageBreak())

    # ------------------------------------------------------------------ watch-list
    S.append(Paragraph('Watch-list: moves that rest on fragile inputs', ST['h1']))
    S.append(Paragraph('These cases would be worth checking before relying on the new ranking for a buy decision. None has been changed in the live scores; each is a candidate for a tweak (for example using the median instead of the mean of the earnings history, or ignoring net cash of banks and insurers).', ST['body']))
    wl = [
        ('UWM Holdings (USA, 457 → 169)', 'Financial. Its net-income history contains one period of $3,382m among values between −$13m and $415m; the 3-year average is $567m versus an average of $18m over the last four periods. The lens C percentile jumps from 17 to 100 on a figure that is almost certainly not a repeatable earnings level.'),
        ('Nanyang Holdings (Asia, 551 → 41)', 'Last-year average net income is −$0.6m and the latest periods are losses (−$15m, −$10m); the 3-year average of $14.5m comes from strong earlier years. Together with $98m of net cash against a $125m market cap (capped at half), lens C reaches the 94th percentile. The biggest rise in the project and a candidate for a manual check.'),
        ('CTT – Correios de Portugal (Europe, 545 → 247)', 'Net cash of about $2.1bn against a ~$955m market cap. The group owns Banco CTT, so the cash line very probably contains customer deposits that are not available to shareholders. The 50% cap limits the effect, but the move should be treated as unverified.'),
        ('Micro-pool climbers on tiny profits (Provide IT Sweden, QubicGames, Kakel Max, CM International, Koszalinskie Przedsiebiorstwo)', 'Their 3-year average profits are $0.1–0.8m on market caps of a few million dollars. Percentile ranking turns these small positive numbers into 69th–99th-percentile scores on lens C, although last year’s average was zero or negative.'),
        ('Companies whose cash is capped (262 in Asia, 48 in Europe, 11 in the micro pool, 6 in the US)', 'The 50% cap is a blunt rule. It prevents extreme boosts but still gives, for example, Soop, Innocean and Stalexport an EV of half their market cap; some of that cash may be restricted or belong to customers.'),
        ('Highly leveraged names with minority interests (Green Cross Holdings, Korea)', '$658m of minority interests means part of the debt belongs to partly-owned subsidiaries; EV as calculated overstates the burden on the parent’s shareholders, so the fall (162 → 545) is probably too severe.'),
        ('BigBen Interactive (micro, 6 → 34)', 'Fundamentals were replaced with the FY to March 2026 results; the company is in an accelerated safeguard procedure and carries a severe-distress flag. A rank of 34 probably remains generous for a company whose shareholders may be heavily diluted or wiped out.'),
    ]
    data = [[Paragraph('Case', ST['hdr']), Paragraph('Why it deserves a second look', ST['hdr'])]]
    for a, b in wl:
        data.append([Paragraph(f'<b>{esc(a)}</b>', ST['cell']), Paragraph(esc(b), ST['cell'])])
    t = Table(data, colWidths=[W * 0.30, W * 0.70], repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), BRAND), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 1), (-1, -1), 0.4, RULE),
                           ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    S.append(t)
    S.append(Spacer(1, 10))
    S.append(Paragraph('Possible refinements', ST['h2']))
    for b in ['Use the <b>median</b> (or a winsorised mean) of the earnings history instead of the mean, so one outsized year cannot dominate.',
              'Require a <b>minimum earnings level</b> (for example 1% of market cap) before a positive 3-year average earns a lens C percentile.',
              'Exclude <b>banks, insurers and bank-owning groups</b> from the net-cash credit.',
              'Reduce the credit for net cash further (for example 25% of market cap) – the ranking changes in the top 50 are modest, so this is a judgement about how far cash should count.']:
        S.append(Paragraph(b, ST['bullet'], bulletText='•'))
    S.append(Spacer(1, 6))
    S.append(Paragraph('Sources: Capital IQ extract (17 March 2026); Yahoo Finance fundamentals feed (balance sheets, mostly March 2026 or later) and company filings for net debt; Yahoo Finance prices (share counts × last close for market caps). '
                       'Before/after tables for the top 50 are in valuation-ev-model.xlsx. “$m” figures are US-dollar millions at current exchange rates.', ST['small']))
    doc.build(S)
    print('wrote', path)


if __name__ == '__main__':
    build(ROOT / 'docs' / 'valuation-ev-movers.pdf')
