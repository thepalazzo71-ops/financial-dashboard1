// ---- 5-year price range columns + "Big swingers" section (shared partial) ----
// Data: c.px = {l: last close, h/lo: 5y closing high/low, hd/ld: their dates, d: date of last
// close, f: first date in window, n: closes, cur: quote currency} from scripts/fetch_price_history.py.
let expandedSwingTicker = null;
const PX_AS_OF = (typeof PAYLOAD !== 'undefined' && PAYLOAD.pxAsOf) || null;
const SW_DEFAULT_MINMC = __SW_DEFAULT_MINMC__;
function pxOf(c) {
  const p = c.px;
  if (!p || !(p.h > 0) || !(p.lo > 0) || !(p.l > 0)) return null;
  return { last: p.l, hi: p.h, lo: p.lo, hd: p.hd, ld: p.ld, d: p.d, f: p.f, cur: p.cur || '', n: p.n,
    vsHi: p.l / p.h - 1, vsLo: p.l / p.lo - 1, range: p.h / p.lo,
    yrs: (Date.parse(p.d) - Date.parse(p.f)) / 31557600000, peakFirst: p.hd < p.ld };
}
function pxPct(v) { return (v < 0 ? '−' : '+') + Math.abs(v * 100).toLocaleString('en-US', { maximumFractionDigits: 0 }) + '%'; }
function pxPrice(v) { return v >= 100 ? fmtNum(v, 0) : (v >= 1 ? fmtNum(v, 2) : fmtNum(v, 4)); }
function pxShortMark(p) { return p.yrs < 4.5 ? `<sup title="Only ${p.yrs.toFixed(1)} years of price history (listed since ${p.f}): high/low cover that window only">&dagger;</sup>` : ''; }
function priceCells(c, isHistorical) {
  const dash = '<td class="num-col num px-cell">—</td>';
  if (isHistorical) return dash + dash;
  const p = pxOf(c);
  if (!p) { const t = '<td class="num-col num px-cell" title="No usable price history (not found, delisted or too little trading history)">—</td>'; return t + t; }
  const tipHi = escHtml(`5-year closing high ${pxPrice(p.hi)} ${p.cur} on ${p.hd}; last close ${pxPrice(p.last)} ${p.cur} (${p.d})`);
  const tipLo = escHtml(`5-year closing low ${pxPrice(p.lo)} ${p.cur} on ${p.ld}; last close ${pxPrice(p.last)} ${p.cur} (${p.d})`);
  return `<td class="num-col num px-cell" title="${tipHi}">${pxPct(p.vsHi)}${pxShortMark(p)}</td><td class="num-col num px-cell" title="${tipLo}">${pxPct(p.vsLo)}</td>`;
}
function priceBox(c) {
  const p = pxOf(c);
  if (!p) return `<div class="px-box"><h4>5-year price range</h4><p class="hint">No usable price history for this company (ticker not found at the price source, delisted, or too little trading history).</p></div>`;
  const item = (l, v, tip) => `<div class="fin-item"${tip ? ` title="${escHtml(tip)}"` : ''}><span class="fin-label">${l}</span><span class="fin-val">${v}</span></div>`;
  const path = p.peakFirst ? `peaked ${p.hd}, bottomed ${p.ld}` : `bottomed ${p.ld}, peaked ${p.hd}`;
  return `<div class="px-box">
    <h4>5-year price range</h4>
    <div class="fin-grid">
      ${item('Last close', pxPrice(p.last) + ' ' + escHtml(p.cur), p.d)}
      ${item('5y high', pxPrice(p.hi) + '<span class="sub" style="display:block;font-weight:400;font-size:11px">' + p.hd + '</span>')}
      ${item('5y low', pxPrice(p.lo) + '<span class="sub" style="display:block;font-weight:400;font-size:11px">' + p.ld + '</span>')}
      ${item('vs 5y high', pxPct(p.vsHi), 'Last close ÷ 5-year closing high − 1')}
      ${item('vs 5y low', pxPct(p.vsLo), 'Last close ÷ 5-year closing low − 1')}
      ${item('Range (high ÷ low)', fmtNum(p.range, 1) + 'x')}
    </div>
    <p class="hint">${path}. Daily closing prices in ${escHtml(p.cur)}, split-adjusted, last close ${p.d}${p.yrs < 4.5 ? `; <b>only ${p.yrs.toFixed(1)} years of history</b> (since ${p.f})` : ''}. Informational: not part of the v6 score.</p>
  </div>`;
}
function renderSwingersContent() {
  const all = ensureLiveScored();
  const rank = computeRankByTicker(all, false);
  const basis = document.getElementById('swBasis').value;
  const minMc = parseFloat(document.getElementById('swMinMc').value) || 0;
  const needLong = document.getElementById('swLong').checked;
  const limit = parseInt(document.getElementById('swN').value, 10);
  const rows = [];
  let withData = 0;
  all.forEach(r => {
    const c = r.c;
    if (typeof isDelisted === 'function' && isDelisted(c.t)) return;
    const p = pxOf(c);
    if (!p) return;
    withData++;
    if (r.mc < minMc) return;
    if (needLong && p.yrs < 3) return;
    rows.push({ r, p });
  });
  const key = { range: x => -x.p.range, drawdown: x => x.p.vsHi, rebound: x => -x.p.vsLo }[basis];
  rows.sort((a, b) => key(a) - key(b));
  // Left: price FELL from its 5-year peak to its trough (peak came first). Right: ROSE (trough came first).
  const fell = rows.filter(x => x.p.peakFirst), rose = rows.filter(x => !x.p.peakFirst);
  const side = (list, title, icon, hint) => {
    const shown = list.slice(0, limit);
    const body = shown.map(({ r, p }, i) => {
      const c = r.c;
      const isOpen = expandedSwingTicker === c.t;
      return `<tr class="sw-row ${isOpen ? 'expanded' : ''}" data-ticker="${c.t}" title="Click for the full company detail">
        <td>${i + 1}</td>
        <td><b>${escHtml(c.n)}</b><div class="sub">${c.t} &middot; ${escHtml(c.co)} &middot; v6 #${rank[c.t]}</div></td>
        <td>${fmtNum(r.mc, 0)}</td>
        <td>${pxPrice(p.hi)}<div class="sub">${p.hd}</div></td>
        <td>${pxPrice(p.lo)}<div class="sub">${p.ld}</div></td>
        <td>${pxPrice(p.last)}<div class="sub">${escHtml(p.cur)}</div></td>
        <td>${pxPct(p.vsHi)}</td><td>${pxPct(p.vsLo)}</td>
        <td><b>${fmtNum(p.range, 1)}x</b>${pxShortMark(p)}</td>
      </tr>`;
    }).join('');
    return `<div class="sw-side">
      <h4>${icon} ${title} <span class="sub">(${list.length}${list.length > shown.length ? `, showing ${shown.length}` : ''})</span></h4>
      <p class="hint" style="margin:0 0 6px">${hint}</p>
      <table class="sw-table">
        <thead><tr><th>#</th><th>Company</th><th>Cap $M</th><th>5y high</th><th>5y low</th><th>Last</th><th>vs high</th><th>vs low</th><th>Range</th></tr></thead>
        <tbody>${body || '<tr><td colspan="9" class="no-thesis">No company matches these filters.</td></tr>'}</tbody>
      </table></div>`;
  };
  const openRow = expandedSwingTicker ? rows.find(x => x.r.c.t === expandedSwingTicker) : null;
  if (expandedSwingTicker && !openRow) expandedSwingTicker = null;
  const detail = openRow ? `<div class="sw-detail-full" id="swDetail">
      <div class="sw-detail-bar"><b>${escHtml(openRow.r.c.n)}</b> <span class="sub">${openRow.r.c.t}</span>
        <button type="button" class="btn ghost small sw-detail-close">Close detail</button></div>
      ${renderDetailPanel(openRow.r, rank[openRow.r.c.t])}
    </div>` : '';
  document.getElementById('swingersContent').innerHTML = detail + `
    <div class="sw-cols">
      ${side(fell, 'Fell', '&#8600;', 'The 5-year high came before the 5-year low: the price dropped from its peak to its trough (it may have bounced since &mdash; see &ldquo;vs low&rdquo;).')}
      ${side(rose, 'Rose', '&#8599;', 'The 5-year low came before the 5-year high: the price climbed from its trough to its peak (it may have slipped back since &mdash; see &ldquo;vs high&rdquo;).')}
    </div>
    <p class="hint" style="margin-top:12px">${rows.length} of ${withData} companies with price history match. Prices are in each company&rsquo;s own trading currency (London shares in pence); &dagger; = less than 4.5 years of history. <b>Click any company</b> to open its full detail.</p>`;
}
function initSwingers() {
  const bd = document.getElementById('swingersModalBackdrop');
  const btn = document.getElementById('swingersBtn');
  if (!bd || !btn) return;
  document.getElementById('swMinMc').value = String(SW_DEFAULT_MINMC);
  btn.addEventListener('click', () => {
    expandedSwingTicker = null;
    document.getElementById('swAsOf').textContent = (typeof PX_AS_OF !== 'undefined' && PX_AS_OF) || 'the last data refresh';
    renderSwingersContent();
    bd.classList.add('open');
  });
  document.getElementById('swingersClose').addEventListener('click', () => bd.classList.remove('open'));
  bd.addEventListener('click', e => { if (e.target === bd) bd.classList.remove('open'); });
  ['swBasis', 'swMinMc', 'swN', 'swLong'].forEach(id => document.getElementById(id).addEventListener('change', () => { expandedSwingTicker = null; renderSwingersContent(); }));
  document.getElementById('swingersContent').addEventListener('click', e => {
    if (e.target.closest('.sw-detail-close')) { expandedSwingTicker = null; renderSwingersContent(); return; }
    const rowEl = e.target.closest('tr.sw-row');
    if (!rowEl) return;
    const t = rowEl.dataset.ticker;
    expandedSwingTicker = (expandedSwingTicker === t) ? null : t;
    renderSwingersContent();
    const d = document.getElementById('swDetail');
    if (d) d.scrollIntoView({ block: 'start', behavior: 'smooth' });
  });
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initSwingers); else initSwingers();
