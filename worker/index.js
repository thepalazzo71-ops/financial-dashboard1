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
//   PUT    /api/comments   edit {ticker,id,text}: replaces the text, stamps `editedAt` (server time)
//   DELETE /api/comments?ticker=..&id=..   remove one comment (and its attachments)
//   PUT    /api/files/<id>   raw file body (<= 10 MB), headers Content-Type + X-File-Name (URL-encoded)
//   GET    /api/files/<id>   the file (images/PDF inline, everything else as a download)
//   DELETE /api/files/<id>   remove an uploaded file (used to clean up an aborted upload)
// A comment may carry up to 5 attachments: [{id, name, size, type}] referring to uploaded files.
//
// Storage: KV binding STATE. Key `comments:<email>` holds the live copy; each
// write also stores a dated copy `backup:<email>:<YYYY-MM-DD>` (180 days) so a
// bug can never destroy the only copy. Attachment bytes live under
// `file:<email>:<id>` (KV value limit 25 MiB; we cap files at 10 MB) - the dated
// backups hold the comment metadata only, not the file bytes.

const JSON_HEADERS = { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' };
const MAX_TEXT = 5000;
const MAX_BYTES = 5 * 1024 * 1024;
const MAX_FILE = 10 * 1024 * 1024;
const MAX_FILES = 5;
const INLINE_TYPES = new Set(['image/png', 'image/jpeg', 'image/gif', 'image/webp', 'application/pdf']);
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

function validAttachments(a) {
  return a === undefined || (Array.isArray(a) && a.length <= MAX_FILES && a.every(x => x && typeof x.id === 'string' && ID_RE.test(x.id)
    && typeof x.name === 'string' && x.name.length > 0 && x.name.length <= 200
    && Number.isFinite(x.size) && x.size >= 0 && x.size <= MAX_FILE
    && typeof x.type === 'string' && x.type.length <= 100));
}
// the stored shape of a comment (only known fields are kept)
function shape(e) {
  const o = { id: e.id, ts: e.ts, text: e.text };
  if (e.editedAt) o.editedAt = e.editedAt;
  if (e.attachments && e.attachments.length) o.attachments = e.attachments.map(a => ({ id: a.id, name: a.name, size: a.size, type: a.type }));
  return o;
}
function validEntry(e) {
  if (!(e && typeof e.ticker === 'string' && e.ticker.length > 0 && e.ticker.length <= 40
    && typeof e.id === 'string' && ID_RE.test(e.id)
    && typeof e.ts === 'string' && !Number.isNaN(Date.parse(e.ts))
    && (e.editedAt === undefined || (typeof e.editedAt === 'string' && !Number.isNaN(Date.parse(e.editedAt))))
    && typeof e.text === 'string' && e.text.length <= MAX_TEXT && validAttachments(e.attachments))) return false;
  return e.text.trim().length > 0 || (e.attachments && e.attachments.length > 0); // text may be empty only with attachments
}
const safeName = (n) => String(n).replace(/[\r\n"\\]/g, '_').slice(0, 200);
async function handleFiles(request, env, email, url) {
  const id = decodeURIComponent(url.pathname.slice('/api/files/'.length));
  if (!ID_RE.test(id)) return bad('bad file id');
  const key = `file:${email}:${id}`;
  if (request.method === 'PUT') {
    const len = Number(request.headers.get('content-length') || 0);
    if (len > MAX_FILE) return bad('file too large (max 10 MB)', 413);
    const buf = await request.arrayBuffer();
    if (buf.byteLength > MAX_FILE) return bad('file too large (max 10 MB)', 413);
    if (buf.byteLength === 0) return bad('empty file');
    let name = 'file';
    try { name = decodeURIComponent(request.headers.get('x-file-name') || 'file'); } catch (e) {}
    const type = (request.headers.get('content-type') || 'application/octet-stream').slice(0, 100);
    await env.STATE.put(key, buf, { metadata: { name: safeName(name), type, size: buf.byteLength } });
    return json({ ok: true, id, size: buf.byteLength });
  }
  if (request.method === 'GET') {
    const r = await env.STATE.getWithMetadata(key, { type: 'arrayBuffer' });
    if (!r || r.value === null) return bad('not found', 404);
    const m = r.metadata || {};
    const type = String(m.type || 'application/octet-stream').split(';')[0].trim().toLowerCase();
    const inline = INLINE_TYPES.has(type);
    return new Response(r.value, { headers: {
      'content-type': inline ? type : 'application/octet-stream',
      'content-disposition': `${inline ? 'inline' : 'attachment'}; filename*=UTF-8''${encodeURIComponent(m.name || 'file')}`,
      'x-content-type-options': 'nosniff',
      ...(inline ? {} : { 'content-security-policy': "default-src 'none'; sandbox" }),
      'cache-control': 'private, max-age=3600',
    } });
  }
  if (request.method === 'DELETE') {
    await env.STATE.delete(key);
    return json({ ok: true });
  }
  return bad('method not allowed', 405);
}

export async function handleApi(request, env) {
  const url = new URL(request.url);
  const email = await authenticate(request, env);
  if (!email) return bad('not authenticated', 401);
  if (!env.STATE) return bad('storage not configured', 503);

  if (url.pathname === '/api/ping') return json({ ok: true, email });
  if (url.pathname.startsWith('/api/files/')) return handleFiles(request, env, email, url);
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
      list.push(shape(e));
      list.sort((a, b) => b.ts.localeCompare(a.ts));
      await store(env, email, s);
    }
    return json({ ok: true });
  }
  if (request.method === 'PUT') {
    let e; try { e = await request.json(); } catch (x) { return bad('invalid JSON'); }
    if (!e || typeof e.ticker !== 'string' || typeof e.id !== 'string' || typeof e.text !== 'string' || e.text.length > MAX_TEXT) return bad('invalid edit');
    const s = await load(env, email);
    const cur = (s.comments[e.ticker] || []).find(x => x.id === e.id);
    if (!cur) return bad('comment not found', 404);
    if (!e.text.trim() && !(cur.attachments && cur.attachments.length)) return bad('text required');
    if (e.text !== cur.text) { cur.text = e.text; cur.editedAt = new Date().toISOString(); await store(env, email, s); }
    return json({ ok: true, editedAt: cur.editedAt || null });
  }
  if (request.method === 'DELETE') {
    const ticker = url.searchParams.get('ticker'), id = url.searchParams.get('id');
    if (!ticker || !id) return bad('ticker and id required');
    const s = await load(env, email);
    if (s.comments[ticker]) {
      const gone = s.comments[ticker].find(x => x.id === id);
      if (gone && gone.attachments) await Promise.all(gone.attachments.map(a => env.STATE.delete(`file:${email}:${a.id}`)));
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
