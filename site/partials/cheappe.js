// ---- "Cheapest by P/E" window (shared partial): P/E and EV / net profit ranking with click-through detail ----
let expandedCpeTicker = null;
const CPE_DEFAULT_COUNTRY = '__CPE_DEFAULT_COUNTRY__';
function cpeLastNi(c) { const h = c.niHist || []; for (let i = h.length - 1; i >= 0; i--) if (h[i] !== null && h[i] !== undefined) return h[i]; return null; }
function renderCheapPeContent() {
  const all = ensureLiveScored();
  const rank = computeRankByTicker(all, false);
  const country = document.getElementById('cpeCountry').value;
  const basis = document.getElementById('cpeBasis').value;
  const minMc = parseFloat(document.getElementById('cpeMinMc').value) || 0;
  const limit = parseInt(document.getElementById('cpeN').value, 10);
  const tenders = new Set(((CORPORATE_ACTIONS && CORPORATE_ACTIONS.tender_offers) || []).map(x => x.ticker));
  const rows = [];
  let pool = 0;
  all.forEach(r => {
    const c = r.c;
    if (typeof isDelisted === 'function' && isDelisted(c.t)) return;
    if (country && c.co !== country) return;
    pool++;
    const ni = cpeLastNi(c);
    if (ni === null || ni <= 0 || !(r.mc > 0) || r.mc < minMc) return;
    const nd = c.nd && c.nd.tier !== 'F' && c.nd.usd !== undefined && c.nd.usd !== null ? c.nd : null;
    const ev = nd ? r.mc + nd.usd : null;
    const evNi = ev !== null && ev > 0 ? ev / ni : null;
    if (basis === 'ev' && !nd) return;
    rows.push({ r, ni, pe: r.mc / ni, nd, ev, evNi });
  });
  const key = x => basis === 'ev' ? (x.evNi === null ? (x.ev !== null && x.ev <= 0 ? -1 : 1e9) : x.evNi) : x.pe;
  rows.sort((a, b) => key(a) - key(b));
  const shown = rows.slice(0, limit);
  const body = shown.map((x, i) => {
    const c = x.r.c, isOpen = expandedCpeTicker === c.t;
    const est = c.mcDerived ? '<span class="est-tag" title="ESTIMATED market cap: the March 2026 Capital IQ value scaled by the price/FX change since then, share count assumed unchanged">est. cap</span>' : '';
    const flags = [];
    if (tenders.has(c.t)) flags.push('tender offer');
    if (c.distress) flags.push(c.distress.level === 'severe' ? 'severe distress' : 'distress warning');
    if (x.nd && (!x.nd.date || x.nd.date === 'unknown')) flags.push('net debt undated');
    if (x.nd && x.nd.tier === 'B') flags.push('reported net debt');
    if (x.pe < 2) flags.push('check one-offs');
    const evCell = x.nd ? (x.ev <= 0 ? 'EV&le;0' : fmtNum(x.evNi, 1) + 'x') : '&mdash;';
    return `<tr class="cpe-row ${isOpen ? 'expanded' : ''}" data-ticker="${c.t}" title="Click for the full company detail">
      <td class="cpc-n">${i + 1}</td>
      <td class="cpc-co"><b>${escHtml(c.n)}</b>${est}<div class="sub">${c.t} &middot; ${escHtml(c.co)} &middot; v6 #${rank[c.t]}</div>${flags.length ? `<div class="flag">${flags.join(' &middot; ')}</div>` : ''}</td>
      <td class="cpc-v">${fmtNum(x.r.mc, 0)}</td>
      <td class="cpc-v">${fmtNum(x.ni, 1)}</td>
      <td class="cpc-v"><b>${fmtNum(x.pe, 1)}x</b></td>
      <td class="cpc-v">${x.nd ? fmtNum(x.nd.usd, 0) : '&mdash;'}</td>
      <td class="cpc-v">${x.nd ? fmtNum(x.ev, 0) : '&mdash;'}</td>
      <td class="cpc-v"><b>${evCell}</b></td>
    </tr>${isOpen ? `<tr class="cpe-open"><td colspan="8" class="cpe-detail-cell">${renderDetailPanel(x.r, rank[c.t])}</td></tr>` : ''}`;
  }).join('');
  document.getElementById('cheapPeContent').innerHTML = `
    <table class="cpe-table">
      <thead><tr><th>#</th><th class="cpc-co">Company</th><th>Mkt cap ($M)</th><th>LTM NI ($M)</th><th>P/E</th><th>Net debt ($M)</th><th>EV ($M)</th><th>EV / net profit</th></tr></thead>
      <tbody>${body || '<tr><td colspan="8" class="no-thesis">No company matches these filters.</td></tr>'}</tbody>
    </table>
    <p class="hint" style="margin-top:12px">${rows.length} of ${pool} companies${country ? ' in ' + escHtml(country) : ''} have positive earnings${rows.length > shown.length ? ` (showing the cheapest ${shown.length})` : ''}. Net debt and EV exist only where it was researched (Europe's top 150 and the cheapest Korean names) and come from the sources noted in the company's detail; &mdash; = not available.</p>`;
}
function initCheapPe() {
  const bd = document.getElementById('cheapPeModalBackdrop'), btn = document.getElementById('cheapPeBtn');
  if (!bd || !btn) return;
  const sel = document.getElementById('cpeCountry');
  const counts = {};
  COMPANIES.forEach(c => { counts[c.co] = (counts[c.co] || 0) + 1; });
  sel.innerHTML = '<option value="">All countries</option>' + Object.keys(counts).sort().map(k => `<option value="${escHtml(k)}">${escHtml(k)} (${counts[k]})</option>`).join('');
  if (CPE_DEFAULT_COUNTRY && counts[CPE_DEFAULT_COUNTRY]) sel.value = CPE_DEFAULT_COUNTRY;
  btn.addEventListener('click', () => { expandedCpeTicker = null; renderCheapPeContent(); bd.classList.add('open'); });
  document.getElementById('cheapPeClose').addEventListener('click', () => bd.classList.remove('open'));
  bd.addEventListener('click', e => { if (e.target === bd) bd.classList.remove('open'); });
  ['cpeCountry', 'cpeBasis', 'cpeMinMc', 'cpeN'].forEach(id => document.getElementById(id).addEventListener('change', () => { expandedCpeTicker = null; renderCheapPeContent(); }));
  document.getElementById('cheapPeContent').addEventListener('click', e => {
    const rowEl = e.target.closest('tr.cpe-row');
    if (!rowEl) return;
    const t = rowEl.dataset.ticker;
    expandedCpeTicker = (expandedCpeTicker === t) ? null : t;
    renderCheapPeContent();
  });
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initCheapPe); else initCheapPe();
