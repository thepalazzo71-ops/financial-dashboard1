// Local test harness (not deployed): runs worker/index.js behind a fake Access
// header with an in-memory KV, serving docs/ as assets, on http://localhost:8787
// Usage: node worker/test_local.mjs
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import worker from './index.js';

const kv = new Map();
const env = {
  STATE: { get: async k => kv.get(k) ?? null, put: async (k, v) => { kv.set(k, v); } },
  ASSETS: { fetch: async req => {
    const p = new URL(req.url).pathname;
    const f = path.join(process.cwd(), 'docs', p === '/' ? 'index.html' : p);
    if (!f.startsWith(path.join(process.cwd(), 'docs')) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) return new Response('nf', { status: 404 });
    return new Response(fs.readFileSync(f), { headers: { 'content-type': f.endsWith('.html') ? 'text/html' : 'application/octet-stream' } });
  } },
};
http.createServer(async (req, res) => {
  const chunks = []; for await (const c of req) chunks.push(c);
  const headers = new Headers(req.headers);
  if (!process.env.NO_ACCESS) headers.set('Cf-Access-Authenticated-User-Email', 'me@example.com');
  const r = new Request(`http://localhost:8787${req.url}`, { method: req.method, headers, body: ['GET','HEAD'].includes(req.method) ? undefined : Buffer.concat(chunks) });
  const out = await worker.fetch(r, env);
  res.writeHead(out.status, Object.fromEntries(out.headers));
  res.end(Buffer.from(await out.arrayBuffer()));
}).listen(8787, () => console.log('listening on 8787'));
