// Cloudflare Worker for the dashboards: serves the static site (docs/) and a
// tiny per-user comments API backed by Workers KV. Everything sits behind
// Cloudflare Access (email one-time-code login), so only approved people reach
// it; comments are keyed to the logged-in email address.
//
// Routes (only /api/* runs this code; static files are served by the assets
// layer - see worker/README.md and wrangler.jsonc):
//   GET    /api/ping                       -> {ok, email}
//   GET    /api/comments                   -> {comments: {ticker: [{id, ts, text}]}, updatedAt}
//   POST   /api/comments  {ticker,id,ts,text}   idempotent add (by id)
//   DELETE /api/comments?ticker=..&id=..   remove one comment
//
// Storage: KV binding STATE. Key `comments:<email>` holds the live copy; each
// write also stores a dated copy `backup:<email>:<YYYY-MM-DD>` (180 days) so a
// bug can never destroy the only copy.

const JSON_HEADERS = { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' };
const MAX_TEXT = 5000;
const MAX_BYTES = 5 * 1024 * 1024;
const ID_RE = /^[A-Za-z0-9_-]{6,40}$/;

const json = (obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: JSON_HEADERS });
const bad = (msg, status = 400) => json({ error: msg }, status);

let certCache = null; // { at, keys }
async function accessKeys(teamDomain) {
  if (certCache && Date.now() - certCache.at < 3600e3) return certCache.keys;
  const r = await fetch(`https://${teamDomain}/cdn-cgi/access/certs`);
  if (!r.ok) throw new Error('cannot fetch Access certs');
  const keys = (await r.json()).keys || [];
  certCache = { at: Date.now(), keys };
  return keys;
}
const b64u = (s) => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(s.length / 4) * 4, '=')), c => c.charCodeAt(0));

// Returns the authenticated email, or null. If ACCESS_TEAM_DOMAIN and
// ACCESS_AUD are configured the Access JWT is verified cryptographically;
// otherwise the Access-injected email header is trusted (safe only while
// every route to this Worker goes through Access - see README).
export async function authenticate(request, env) {
  const jwt = request.headers.get('Cf-Access-Jwt-Assertion');
  if (env.ACCESS_TEAM_DOMAIN && env.ACCESS_AUD) {
    if (!jwt) return null;
    try {
      const [h, p, s] = jwt.split('.');
      const header = JSON.parse(new TextDecoder().decode(b64u(h)));
      const payload = JSON.parse(new TextDecoder().decode(b64u(p)));
      const jwk = (await accessKeys(env.ACCESS_TEAM_DOMAIN)).find(k => k.kid === header.kid);
      if (!jwk) return null;
      const key = await crypto.subtle.importKey('jwk', jwk, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify']);
      const ok = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, b64u(s), new TextEncoder().encode(`${h}.${p}`));
      const aud = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
      if (!ok || !aud.includes(env.ACCESS_AUD) || payload.exp * 1000 < Date.now() || !payload.email) return null;
      return String(payload.email).toLowerCase();
    } catch (e) { return null; }
  }
  const email = request.headers.get('Cf-Access-Authenticated-User-Email');
  return email ? email.toLowerCase() : null;
}

async function load(env, email) {
  const raw = await env.STATE.get(`comments:${email}`);
  if (!raw) return { comments: {}, updatedAt: null };
  try { const d = JSON.parse(raw); return { comments: d.comments || {}, updatedAt: d.updatedAt || null }; }
  catch (e) { return { comments: {}, updatedAt: null }; }
}
async function store(env, email, state) {
  state.updatedAt = new Date().toISOString();
  const body = JSON.stringify(state);
  if (body.length > MAX_BYTES) throw new Error('comment store too large');
  await env.STATE.put(`comments:${email}`, body);
  await env.STATE.put(`backup:${email}:${state.updatedAt.slice(0, 10)}`, body, { expirationTtl: 180 * 86400 });
}

function validEntry(e) {
  return e && typeof e.ticker === 'string' && e.ticker.length > 0 && e.ticker.length <= 40
    && typeof e.id === 'string' && ID_RE.test(e.id)
    && typeof e.ts === 'string' && !Number.isNaN(Date.parse(e.ts))
    && typeof e.text === 'string' && e.text.trim().length > 0 && e.text.length <= MAX_TEXT;
}

export async function handleApi(request, env) {
  const url = new URL(request.url);
  const email = await authenticate(request, env);
  if (!email) return bad('not authenticated', 401);
  if (!env.STATE) return bad('storage not configured', 503);

  if (url.pathname === '/api/ping') return json({ ok: true, email });
  if (url.pathname !== '/api/comments') return bad('not found', 404);

  if (request.method === 'GET') {
    const s = await load(env, email);
    return json({ comments: s.comments, updatedAt: s.updatedAt });
  }
  if (request.method === 'POST') {
    let e; try { e = await request.json(); } catch (x) { return bad('invalid JSON'); }
    if (!validEntry(e)) return bad('invalid comment');
    const s = await load(env, email);
    const list = s.comments[e.ticker] = s.comments[e.ticker] || [];
    if (!list.some(x => x.id === e.id)) {
      list.push({ id: e.id, ts: e.ts, text: e.text });
      list.sort((a, b) => b.ts.localeCompare(a.ts));
      await store(env, email, s);
    }
    return json({ ok: true });
  }
  if (request.method === 'DELETE') {
    const ticker = url.searchParams.get('ticker'), id = url.searchParams.get('id');
    if (!ticker || !id) return bad('ticker and id required');
    const s = await load(env, email);
    if (s.comments[ticker]) {
      s.comments[ticker] = s.comments[ticker].filter(x => x.id !== id);
      if (!s.comments[ticker].length) delete s.comments[ticker];
      await store(env, email, s);
    }
    return json({ ok: true });
  }
  return bad('method not allowed', 405);
}

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    if (pathname.startsWith('/api/')) {
      try { return await handleApi(request, env); }
      catch (e) { return bad('server error', 500); }
    }
    return env.ASSETS.fetch(request);
  },
};
