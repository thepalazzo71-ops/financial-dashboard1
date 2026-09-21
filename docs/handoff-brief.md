# European Small/Mid-Cap Value Shortlist — Handoff Brief for Claude Code

## What this project is

A value-investing dashboard that screens ~6,109 raw European small/mid-cap
companies (US$15M–1B market cap) down to a ranked top-150 shortlist using a
documented 9-dimension scoring system ("v6"), and keeps that shortlist live
by periodically refreshing market caps (and eventually gross margins) for
the companies in it.

The heavy lifting — universe construction, quality gates, gross-margin
research — was already done once and is captured in two source files (see
below). What's ongoing now is a **market-cap refresh loop**: working through
the shortlist in batches, pulling current market caps from a data provider,
sanity-checking them, and pushing them into a live dashboard.

## Source files (need to be re-uploaded / relocated for Code)

These were uploaded into the chat project and processed into working files
in a `/home/claude/work/` scratch directory that does **not** persist
between chat sessions. You'll want to either re-export the working files
from a Claude.ai chat before switching, or rebuild them from the original
source files:

- `Europe_15m-1B.xls` — raw Capital IQ extract, 6,109 companies, 87 columns
  (revenue, net income, CFO, shares outstanding, dividends, long-term debt;
  10 quarterly LTM snapshots each, LTM-36 through LTM). **Now saved in the
  repo at `data/raw/Europe_15m-1B.xls`** — it was needed to fix a real
  scoring gap (see below) and is the only source for shares-outstanding
  history, so don't lose it again.
- `European_Shortlist_Methodology.docx` — the full methodology write-up
  (also attached to this chat as a project file). This is the source of
  truth for every filter/formula below.
- `European_SmallMidCap_Value_Shortlist.xlsx` — a prior AI-generated run:
  top-150 with scores, investment theses, red flags, shareholders, full
  financial history. Useful as a reference/sanity-check dataset.
- `European_GM_Research_Data.xlsx` — gross-margin research for the top-1000
  candidate pool (790/1000 companies covered from official filings; 210
  fall back to the pool median GM score).

**Recommendation:** ask me (in a Claude.ai chat) to export
`companies_1000_scored.json` (the fully-scored 1000-company pool — see
below) as a downloadable file before you start in Code, so you don't have
to rebuild the ingestion pipeline from scratch.

## The v6 scoring model (100 points, 9 dimensions)

Reconstructed from the methodology doc since the original scoring script
wasn't available. Full detail is in `European_Shortlist_Methodology.docx`;
summary:

| Dimension | Points | Basis |
|---|---|---|
| Revenue Growth | 6 | power(0.4) curve on (latest/earliest − 1), capped at 300% |
| Revenue Consistency | 12 | % of sequential period-over-period increases |
| Dilution | 12 | banded: full marks ≤10% lifetime share-count growth, partial 10–15%, penalized 15–20% |
| Quality-Adj Valuation | 18 | best-of-3 lenses, **percentile-ranked across the full 1000-company pool** (not just the top 150) |
| Profitability | 16 | % of reported NI periods positive |
| CFO Positive | 6 | % of reported CFO periods positive |
| Track Record | 8 | linear on # periods reported, capped at 10 |
| Dividend Consistency | 4 | % of periods with a dividend paid |
| Gross Margin | 18 | banded (≥60%→18.0 down to <5%→0.0); missing GM → pool median fallback |

**Valuation lenses** (company gets credit on whichever is best):
- Lens A (GM-adjusted P/S) = (MktCap / Rev_LTM) / GM — lower better
- Lens B (ROE-adjusted P/B) = (MktCap / Equity) / max(ROE_recent/10%, 0.1) — lower better
- Lens C (growth-adj earnings yield) = (avg_recent_NI / MktCap) × (1 + min(rev_growth, 2.0)) — higher better

ROE uses the average of the **four most-recent** NI periods over **current**
equity (not average-of-all-periods — v6 fixed a v5 distortion here).

Upstream of scoring: quality gates (track record ≥7/10 periods, all
positive revenue, dilution ≤20%, positive revenue growth, positive equity,
≥50% profitable periods) reduced 7,292 operating companies to 1,816
survivors; the top 1,000 of those (by a preliminary pre-GM score) form the
scoring pool that everything above operates on.

## Dashboard

Published at: **https://claude.ai/artifact/WJD9KPY74x2MpxwATWixka**

Architecture:
- Static financial data for all 1,000 companies (~1MB) is embedded directly
  in the page's HTML at build time.
- A dynamic overrides layer — market-cap overrides and (eventually)
  gross-margin overrides — lives in the Artifact tool's `db` capability,
  in two collections: `overrides` (keyed by ticker, e.g. `AIM:OMG`,
  fields `mc`, `source`, `updatedAt`) and `gmOverrides` (not yet used).
  The page has a live `onSnapshot` subscription, so writes to `db` show up
  in the dashboard without a reload.
- Every market-cap (or future GM) update — whether from the dashboard's own
  UI buttons or written directly by Claude — must save a dated `.xlsx`
  snapshot of full dashboard state *first*, for historical record-keeping.
  In-browser this uses SheetJS + the `downloads` capability; on the
  automation side it's mirrored by `snapshot.py` (below).
- Capabilities declared on the artifact: `db`, `downloads`.

If Claude Code doesn't have the Artifact tool available the way claude.ai
chat does, the practical options are: (a) keep doing dashboard updates from
a claude.ai chat session while Code handles data-gathering/computation, or
(b) have Code write to a local file/DB and periodically sync into the
dashboard's `db` from a chat session. Worth checking what's actually
available before assuming full parity.

## Market-cap refresh workflow (per batch of 30 companies)

This is the loop that's been running, and that Code should be able to
script end-to-end once connectors are in place:

1. Pull the next 30 tickers by v6 rank from the scored pool
   (`companies_1000_scored.json`, sorted by `total` descending).
2. Resolve each company to a market-data entity ID (`find_securities` by
   name + country in Bigdata.com — Twelve Data's market-cap endpoints are
   paywalled on the current plan, and FactSet errored out with
   `ofid_4453cc0306c1324f`, unresolved as of this writing).
3. Batch-fetch market cap + price for all resolved entities in one call
   (`bigdata_portfolio_tearsheet`, ~28 entities per call comfortably).
   **Market cap comes back in local currency, not USD.**
4. Convert to USD via `Twelve Data: currency_conversion` (this endpoint is
   unrestricted even on the free/current plan).
   - Watch for ambiguous currency symbols: "kr" is SEK (Sweden), NOK
     (Norway), or DKK (Denmark) depending on the exchange — resolve from
     the listing, not the symbol. Also watch for ISK, PLN, GBP, EUR, CHF.
   - FX rates are a point-in-time snapshot and should be refreshed each
     batch, not reused indefinitely.
5. Sanity-check each converted value against the original `mc0` baseline.
   Flag or exclude anything wildly implausible (a >5–10x swing is a strong
   signal of a data error, e.g. a currency mix-up or wrong entity match —
   this has happened at least twice: Gérard Perrier Industrie returned
   ~20-40x too high, Delta Plus Group returned literally $0.00). Note but
   keep large-but-plausible swings (e.g. Halfords Group +87% — checked out
   as a real price/share-count move, not an error).
6. Regenerate and save a pre-update snapshot (`snapshot.py`, updating its
   `mc_overrides` dict with the batch about to be written) before writing
   anything.
7. Write the batch to the dashboard's `overrides` collection as one atomic
   batch write, keyed by ticker.

**Known non-coverage** (companies Bigdata.com couldn't resolve or had no
market data for, across batches run so far — don't re-attempt these
without a different data source): Amhult 2 AB, Poulaillon SA, Müller-Die
lila Logistik SE, HomeMaid AB, Atlantic Insurance, Société Centrale des
Bois et des Scieries de la Manche, Poujoulat SA, Ilirija d.d., Paul
Hartmann AG, Agria Group Holding, Biofarm S.A., XBS Pro-Log S.A., Blue Cap
AG (listing missing from Bigdata's knowledge graph despite being publicly
traded), InnoTec TSS AG, TF Bank AB (only a private Finnish subsidiary
resolves, not the Swedish public parent), Medika d.d., Sopharma Trading
AD, TOMA a.s., AB Zemaitijos pienas, Messer Tehnogas AD, BasicNet S.p.A.,
Comvex S.A., Reti S.p.A., ILPRA S.p.A., Slatinska Banka d.d.

**Excluded — data errors** (resolved with a value, but the value itself is
implausible and not applied): Gérard Perrier Industrie (~20-40x too high),
Delta Plus Group (returned $0.00), Maschinenfabrik Berthold Hermle AG
(market cap exactly equaled price × 1,000,000 — a placeholder, not a real
share count), Maisons du Monde S.A. (quoted price of €0.233/share is far
below its normal trading range).

## Major fix: dilution scoring gap (2026-09-21)

The user asked why ProCook Group plc (LSE:PROC) wasn't in the shortlist
anymore — a prior AI-generated run (20 Mar 2026, uploaded as
`European_SmallMidCap_Value_Shortlist_2.xlsx`) had it ranked **#100**;
the current pool had it at **#508**. Root cause: ProCook's `dilution`
field in `data/companies_1000_scored.json` was `null`, which the model
scores as **0/12 dilution points** — the harshest possible penalty — even
though ProCook's actual lifetime share growth (6.7%, comfortably in the
full-marks band) was known in the March run.

**This wasn't isolated to ProCook.** 84 of the 1,000 companies in the pool
had `dilution: null`. The scored-pool JSON simply never carried a
shares-outstanding history (`revHist`/`niHist` exist per company, no
`sharesHist`) — it wasn't a computation bug, the input was missing.

The user supplied the original raw Capital IQ extract
(`data/raw/Europe_15m-1B.xls`), which has a
"Weighted Avg. Diluted Shares Out." column for the same 10 LTM periods
already used for revenue/NI. `scripts/fix_dilution_gaps.py` recomputes
dilution from that raw data using the exact same formula already implied
by the ~900 companies that did have a value (reverse-engineered from
existing (dilution, points) pairs and cross-checked against several
known-good companies before use — see the script's docstring for the
formula and full derivation).

**Result:** 69 of the 84 gaps were fixed (real shares data existed once
Capital IQ's `0.0` "not reported" placeholder was correctly filtered
out — 0 diluted shares outstanding isn't possible for a real company).
The other 15 have no shares data at all across any of the 10 periods and
remain unresolved. Recomputing 69 companies' scores reshuffled the whole
pool's ranking; **12 companies entered the top 150 and 12 exited**
(all from the bottom of the old list) — see git history on
`data/companies_1000_scored.json` for the exact before/after. The 12 new
entrants didn't have a market-cap override yet at that point and were
refreshed in the batch right after (see below).

If more `dilution: null` gaps turn up elsewhere in the pool (outside the
top 150) or new data sources are added, re-run
`python3 scripts/fix_dilution_gaps.py` then `scripts/build_site.py` —
it's idempotent and safe to run repeatedly.

## Rank-sync policy (2026-09-21)

The user caught a real bug: after refreshing ProCook's market cap
(higher price -> worse P/S and P/B lenses -> lower valuation score, as a
value model should behave), its `rankFull` in the JSON still said #77 —
stale, computed before that refresh. The live dashboard was already
correct (it recomputes rank in-browser from current overrides on every
load); only the **stored** `rankFull` had drifted, because nothing had
been resyncing it after routine market-cap batches, only after model
fixes like the dilution gap.

Fixed properly: `scripts/build_site.py` now calls
`scoring.resync_pool_ranks()` on every run, which recomputes valPts/
gmPtsUsed/total/rankFull for the whole pool from current overrides
(mc0/gm baselines are untouched) and persists that back into
`data/companies_1000_scored.json` before building the site. Since
valuation is percentile-ranked across the whole pool, **every** company's
score can shift slightly whenever *any* single company's price changes —
not just the ones that were directly refreshed — so top-150 membership
can churn a little on every rebuild now, which is expected and correct
(it's what "live" means for a percentile-ranked model). A standalone
`scripts/resync_ranks.py` does the same resync without a full rebuild, if
ever needed on its own.

Anything reading `rankFull` (batch selection, coverage counts, `rank`
in `scripts/build_movers_report.py`-style reports) is now guaranteed
current as of the last `build_site.py` run — no more manual step to
remember, and no more silently-stale numbers like the "#77" reported to
the user before this fix.

## History feature + baseline-vs-live convention (2026-09-21)

Added a read-only history dropdown to the dashboard (`#historyDate` in
`site/template.html`) so past states of the shortlist can be viewed
without leaving the live page. This surfaced a second real data-integrity
issue the user caught: the obvious approach — embedding whichever dated
`.xlsx`/`.json` snapshots happened to already exist in `snapshots/` —
would have exposed the buggy pre-dilution-fix state as if it were a
legitimate "before" point. E.g. the 2026-09-20 snapshot had ProCook Group
at rank 511 (dilution pts 0, the missing-data bug fixed above), not its
true baseline rank.

**Fixed by not trusting dated files for the "before" comparison at all.**
`scripts/scoring.py` now has `compact_snapshot_rows(companies,
mc_overrides, gm_overrides)`, and `scripts/build_site.py`'s `load_history()`
always computes a **`baseline`** entry fresh — `compact_snapshot_rows(companies,
{}, {})`, i.e. original market caps, zero refresh-project overrides,
against the *current* (already dilution-corrected) pool. This is the only
"before" state used anywhere now: it can never go stale or carry a
since-fixed bug, because it's recomputed at every build rather than read
from a file captured mid-project. `snapshots/shortlist_snapshot_*.json`
files (any captured going forward, after this fix) load in addition to
`baseline` as ordinary dated history entries.

Two backfilled snapshot JSONs from before this fix
(`shortlist_snapshot_2026-09-20.json`, `_2026-09-21.json`) were deleted —
one had the dilution bug, the other duplicated live exactly, neither was
a useful history entry. The `.xlsx` audit-trail files for those dates are
untouched.

**Note on the pre-2026-09-21 "#100" figure**: the original AI-run
shortlist (`European_SmallMidCap_Value_Shortlist_2.xlsx`, outside this
repo) had ProCook at rank ~100. This codebase's `baseline` (zero
overrides, dilution correct) computes it at **rank 77**, not 100 — a
pre-existing methodology difference between that original run and this
v6 reimplementation, already covered by the "Formula note" disclaimer on
the dashboard. It predates and is unrelated to the dilution bug or the
market-cap refresh project, so **77 → 142** (baseline → live) is the
correct comparison, not 100 → 142 or 508 → 142.

`scratch/build_rank_movers.py` (rank-movers report) and
`scratch/build_movers_report.py` (market-cap movers report) both use this
same baseline-vs-live convention now — `score_pool(companies, {}, {})` vs
`score_pool(companies, mc_overrides, gm_overrides)` — for any "before vs
after" analysis, rather than diffing two arbitrary git commits or dated
files.

**Standing policy — freeze a dated snapshot before every override batch.**
The user wants past dashboard states preserved permanently as new batches
land, not just `baseline` vs whatever is currently live. So: **before**
applying any new `data/mc_overrides_applied.json` /
`data/gm_overrides_applied.json` batch, run `python3 scripts/snapshot.py`
first (no args = today's date) to freeze the current live state to
`snapshots/shortlist_snapshot_<date>.json` (+ matching `.xlsx`). That file
is then a permanent, never-overwritten history entry (the dashboard's
`load_history()` in `scripts/build_site.py` picks up every
`snapshots/shortlist_snapshot_*.json` file automatically) — apply the
batch and rebuild *after*, so "today's before" and "today's after" don't
collide. If a batch is applied same-day as an earlier one, re-running
`scripts/snapshot.py` same-day overwrites that day's file with the latest
pre-batch state, which is correct (one frozen point per calendar day, not
per batch). A first such snapshot (2026-09-21, today's fully-refreshed
133-override state at the time of this fix) already exists as the
baseline for this policy going forward.

The dashboard's history dropdown shows `baseline` first, then every
frozen date, each formatted as "As of D Mon YYYY" (see `formatDateKey` /
`historyLabel` in `site/template.html`). Every history entry is embedded
directly in `docs/index.html` at build time (the user's explicit choice
over a lazy-load approach) — the file grows by roughly the size of one
full-pool snapshot (~250 KB minified JSON) per frozen date, so if batches
start landing very frequently this may eventually need a lazy-load
mechanism instead of full embedding; not a concern at the current cadence.

## Fundamental-catalyst news notes (2026-09-21)

The user wants the detail panel to explain, for big rank movers
specifically, *why* — whether some real fundamental event (earnings,
guidance, M&A, a contract, regulatory news, leadership change...)
between the baseline extract and today plausibly caused the move, not
just "the market cap changed." This is manually/agent-researched, not
computed: `data/company_news.json` is `{ticker: {note, confidence}}`,
loaded by `scripts/build_site.py`'s `load_company_news()` and embedded
as `c.newsNote` in the payload. A missing ticker means no attributable
catalyst was found or it hasn't been researched yet — both are normal;
most rank moves are pure pool-ripple (no news of their own at all, see
the rank-movers report) or a plain re-rating with no distinct trigger,
so **most companies should have no note**, and that's correct, not a gap.
`site/template.html`'s detail panel shows a gold "What likely moved the
rank" callout right at the top when `c.newsNote` is set, above the
existing lens-note; nothing renders when it's absent.

Scope so far: researched the 25 companies with the single biggest
baseline→live rank swings among the 133 whose own market cap was
actually refreshed (the ones in `scratch/rank_movers.xlsx`'s "Biggest
Rank Gains"/"Biggest Rank Declines" tabs) — not all 133, and not the
620 pure-ripple movers (which by definition have no company-specific
news to find). Found an attributable catalyst for 17/25 (in
`data/company_news.json`); 8 came back with no clear finding
(ALLUX, LSC, FOI B, EVS, CMO, OGUN B, GE, FQT — no coverage in
Bigdata.com, or the news found didn't fit the direction/magnitude of
the move, so correctly left blank rather than guessed). To extend
coverage, research more tickers the same way (Bigdata.com search/
tearsheet for a fundamental catalyst in the baseline-to-live window,
one factual sentence, skip if nothing attributable turns up) and add
entries to `data/company_news.json`, then rebuild.

**Flagged data-quality issue — ENXTPA:CMO (Caisse Régionale de Crédit
Agricole du Morbihan) baseline looks wrong.** The rank-movers research
turned this up: its baseline `mc0` is $630.4M vs. a live override of
$200.55M, a -68.2% move that looks implausible for a stable regional
bank cooperative, and no news search explained it. Checked directly
against Bigdata.com's own live company tearsheet for this ticker
(rp_entity_id `F0D661`, XPAR:CMO): current market cap is €183.9M —
consistent with the live override — but the stock's own 6-month price
change is **+15.4%** (i.e. the price is *up* since ~March 2026, the
baseline extract date), which is inconsistent with a market cap that's
supposedly down 68% over the same window. That points to the
**baseline** `mc0` value being wrong (likely a bad share count or
similar in the original Capital IQ extract for this one ticker), not
the refreshed live value, which independently checks out. Not fixed
yet — flagged for the user rather than corrected unilaterally, per the
project's rule against hand-editing scores/rankings without a clear,
verified cause (same standard applied to the 2026-09-21 dilution fix).
If confirmed, the fix is a `data/companies_1000_scored.json` correction
to this one ticker's `mc0`, the same pattern as `fix_dilution_gaps.py`.

A new **Δ (rank change)** column sits right after `#` in the main table,
on every view (live and historical alike) — an up/down arrow plus the
number of places moved, comparing the row's rank in the view you're on
against its rank in the checkpoint immediately before it
(`previousHistoryKey()`/`rankDeltaMap()` in `site/template.html`): for
`live` that's the most recent frozen snapshot (or `baseline` if none has
been frozen yet); for a dated snapshot it's whichever checkpoint precedes
it; `baseline` itself (nothing precedes it) shows an em dash. This is
exactly why the snapshot-before-every-batch policy above matters — the Δ
column is only meaningful once there's a prior frozen point to diff
against, so skipping a pre-batch snapshot leaves "live" comparing itself
to a stale or absent baseline.

## Progress as of this handoff

- **133 of 150** shortlist companies have refreshed market caps — every
  company in the (post dilution-fix) top 150 that Bigdata.com can resolve
  to a real market cap now has one, including all 8 of the 12 new
  entrants from the dilution fix (4 more non-coverage names). The
  remaining 17 gaps are known non-coverage or excluded data errors (see
  above); don't re-attempt without a different data source.
- Market-cap refresh for the top 150 is effectively **done** for now.
  Remaining related work: gross-margin research (still deferred, see
  below), and re-attempting non-coverage names only if a new data source
  becomes available.

## Explicitly deferred / future work

- Completing gross-margin research for the 210 "needs GM" companies in the
  top-1000 pool (same Claude-mediated workflow as market cap: research from
  official filings only — no third-party aggregators — write to
  `gmOverrides`).
- Once the European dashboard is in steady state, the same pipeline will be
  applied to other geography/market-cap datasets the user will provide.
- Spin-off / special-situation detection — explicitly deferred to the "last
  part of the project" per the original brief. Not started.

## Source-rule constraints worth preserving

Per explicit user instruction, gross-margin research must come **only**
from company-published documents and exchange filings (annual reports, IR
pages, earnings releases, exchange filings). Third-party aggregators
(SimplyWall.st, Yahoo Finance, Stockanalysis.com, Macrotrends, WSJ,
Reuters/Bloomberg profiles) are explicitly excluded as sources. Watch for
UK retailers bundling store wages/property into "Cost of Sales" (the Card
Factory pattern) — use the company-disclosed product margin instead when
that's detected.

No manual additions or removals to the final ranked list — if a company is
missed, the fix is to refine the model, not hand-edit the output. The one
standing exception is Card Factory, where a methodological GM input error
was corrected.
