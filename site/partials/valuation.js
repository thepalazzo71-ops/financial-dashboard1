// ---- Valuation helpers shared with the dashboards that lack them (Europe's template defines its own; those win) ----
if (typeof valuationBox !== 'function') {
window.ltmNI = function(c) {
  const h = c.niHist || [];
  for (let i = h.length - 1; i >= 0; i--) if (h[i] !== null && h[i] !== undefined) return h[i];
  return null;
};
window.valuationOf = function(c, mc) {
  const nd = c.nd;
  const out = { nd, ndUsd: null, ev: null, ni: (nd && nd.niUsd !== null && nd.niUsd !== undefined) ? nd.niUsd : ltmNI(c), evE: null, pe: null, fin: !!(nd && nd.tier === 'F') };
  if (mc !== null && mc !== undefined && out.ni !== null && out.ni > 0) out.pe = mc / out.ni;
  if (!nd || nd.tier === 'F' || mc === null || mc === undefined) return out;
  out.ndUsd = nd.usd; out.ev = mc + nd.usd;
  if (out.ni !== null && out.ni > 0 && out.ev > 0) out.evE = out.ev / out.ni;
  return out;
};
window.ndBasisText = function(nd) {
  const m = v => v === null || v === undefined ? '—' : fmtNum(v, 1);
  const when = (nd.date || '?') + (nd.per ? ' ' + nd.per.replace('_', '-') : '');
  if (nd.tier === 'A') return `Debt ${nd.cur} ${m(nd.gd)}m − cash ${nd.cur} ${m(nd.cash)}m = ${nd.cur} ${m(nd.local)}m net debt at ${when}` + (nd.lease !== null && nd.lease !== undefined ? ` (lease liabilities ${nd.cur} ${m(nd.lease)}m excluded)` : '');
  return `Company-reported net debt ${nd.cur} ${m(nd.local)}m at ${when}; the company's own definition (leases, pensions, "adjusted") varies`;
};
window.valuationBox = function(row) {
  const { c, mc, pb } = row;
  const v = valuationOf(c, mc), nd = c.nd;
  if (v.fin) return `<div class="val-box"><h4>Valuation</h4><p class="hint">Enterprise value is not meaningful for banks, insurers and other financial companies, so no net debt or EV / earnings is shown.</p></div>`;
  if (!nd) return `<div class="val-box"><h4>Valuation</h4><p class="hint">No net-debt data yet &mdash; it was researched for Europe&rsquo;s top 150 and for the cheapest companies by P/E in Europe and Asia, and was either not found or not yet looked up for this company, so EV and EV / earnings are not available. P/E (market cap &divide; LTM net income): ${v.pe !== null ? fmtNum(v.pe, 1) + 'x' : 'n/m'}.</p></div>`;
  const item = (l, val, tip) => `<div class="fin-item"${tip ? ` title="${escHtml(tip)}"` : ''}><span class="fin-label">${l}</span><span class="fin-val">${val}</span></div>`;
  const lease = nd.lease !== null && nd.lease !== undefined ? nd.lease * (nd.fx || 0) : null;
  const flags = (nd.flags || []).filter(f => f !== 'company-reported net debt only');
  return `<div class="val-box">
    <h4>Valuation &mdash; enterprise value</h4>
    <div class="fin-grid val-grid">
      ${item('Market cap', '$' + fmtNum(mc, 1) + 'M', 'Live market cap (reflects any edit you made)')}
      ${item('Net debt', (v.ndUsd < 0 ? '−' : '') + '$' + fmtNum(Math.abs(v.ndUsd), 1) + 'M' + (v.ndUsd < 0 ? ' (net cash)' : ''))}
      ${item('Enterprise value', (v.ev < 0 ? '\u2212' : '') + '$' + fmtNum(Math.abs(v.ev), 1) + 'M' + (v.ev < 0 ? ' (net cash exceeds market cap)' : ''), 'Market cap + net debt')}
      ${item('LTM net income', v.ni !== null ? '$' + fmtNum(v.ni, 1) + 'M' : '—', nd.niNote || 'Last-twelve-months net income from the data extract')}
      ${item('EV / earnings', v.evE !== null ? '<b>' + fmtNum(v.evE, 1) + 'x</b>' : (v.ni !== null && v.ni <= 0 ? 'n/m (loss-making)' : (v.ev <= 0 ? 'n/m (EV ≤ 0)' : '—')), 'Enterprise value ÷ last-twelve-months net income')}
      ${item('P/E', v.pe !== null ? fmtNum(v.pe, 1) + 'x' : 'n/m', 'Market cap ÷ last-twelve-months net income, for comparison')}
      ${lease !== null ? item('EV incl. leases', '$' + fmtNum(v.ev + lease, 1) + 'M', 'EV plus IFRS 16 lease liabilities of $' + fmtNum(lease, 1) + 'M') : ''}
    </div>
    <p class="hint val-basis"><b>Net debt basis (tier ${nd.tier}):</b> ${escHtml(ndBasisText(nd))}.${nd.src ? ` <a href="${escHtml(nd.src)}" target="_blank" rel="noopener">source</a>` : ''}${nd.srcType ? ` (${escHtml(String(nd.srcType).replace(/_/g, ' '))})` : ''}</p>
    ${flags.length ? `<p class="hint val-basis" style="color:var(--brick)">&#9888; ${flags.map(escHtml).join(' &middot; ')}</p>` : ''}
    ${nd.niNote ? `<p class="hint val-basis"><b>Net income basis:</b> ${escHtml(nd.niNote)}</p>` : ''}
    <p class="hint val-basis">Converted to USD at an approximate mid-2026 rate (${escHtml(nd.cur)} ${nd.fx}); EV / earnings uses net income, not EBIT. Informational: not part of the v6 score.</p>
  </div>`;
};
}
