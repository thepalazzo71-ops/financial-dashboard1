# Comments API (Cloudflare Worker + KV)

`worker/index.js` is a small Worker that sits in front of the static site (`docs/`)
and adds `/api/comments` so the dashboards can save the user's per-company
comments in **Cloudflare KV** (durable, synced across devices) instead of only in
the browser. Everything is behind **Cloudflare Access** (email one-time code); the
Worker keys each person's comments to their Access email.

**Status: code written and tested locally, NOT activated.** `wrangler.jsonc` still
deploys static assets only. Until the steps below are done the pages simply fall
back to browser-only comments (+ Export / `data/comments.json`).

## Activation (needs the user's Cloudflare account)

1. **Create a KV namespace** (name e.g. `financial-dashboard-state`) - Cloudflare
   dashboard -> Storage & Databases -> KV -> Create, or let Claude do it after
   the user authorizes the Cloudflare connector. Note its **namespace ID**.
2. **Replace `wrangler.jsonc`** with the content of `worker/wrangler.activated.jsonc`
   (fill in the KV id). It adds `main`, the `ASSETS` binding, `run_worker_first`
   for `/api/*` only, the `STATE` KV binding and `preview_urls: false`.
3. **Push to the branch Cloudflare deploys from** (Workers Builds). Confirm the
   Access application still covers *all traffic* on the Worker's hostname -
   `/api/*` must be behind Access (it is when Access protects the whole
   workers.dev domain, as the README describes).
4. *(Optional hardening)* set Worker variables `ACCESS_TEAM_DOMAIN`
   (`<team>.cloudflareaccess.com`) and `ACCESS_AUD` (the Access application's AUD
   tag) so the Worker verifies the Access JWT itself instead of trusting the
   email header. Without them it trusts `Cf-Access-Authenticated-User-Email`,
   which is safe only while every route to the Worker goes through Access.

## API

| Route | Purpose |
|---|---|
| `GET /api/ping` | `{ok, email}` |
| `GET /api/comments` | `{comments: {ticker: [{id, ts, text}]}, updatedAt}` |
| `POST /api/comments` | add `{ticker, id, ts, text}` (idempotent by id; text <= 5000 chars) |
| `DELETE /api/comments?ticker=..&id=..` | remove one comment |

KV keys: `comments:<email>` (live) and `backup:<email>:<YYYY-MM-DD>` (dated copy
on every write, kept 180 days).

## Local test

`node worker/test_local.mjs` serves `docs/` plus the API on http://localhost:8787
with an in-memory store and a fake Access email header (set `NO_ACCESS=1` to see
the 401 / browser-only fallback).
