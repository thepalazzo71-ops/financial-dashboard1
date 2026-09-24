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

**Standing policy — freeze a dated snapshot BEFORE every override batch,
never after.** The user wants past dashboard states preserved
permanently as new batches land, not just `baseline` vs whatever is
currently live. So: **before** applying any new
`data/mc_overrides_applied.json` / `data/gm_overrides_applied.json`
batch, run `python3 scripts/snapshot.py` first (no args = today's date)
to freeze the current live state to
`snapshots/shortlist_snapshot_<date>.json` (+ matching `.xlsx`) — *then*
apply the batch and rebuild. That file becomes a permanent, never-
overwritten history entry (`load_history()` in `scripts/build_site.py`
picks up every `snapshots/shortlist_snapshot_*.json` file automatically).
If a batch is applied same-day as an earlier one, re-running
`scripts/snapshot.py` same-day overwrites that day's file with the
latest pre-batch state (one frozen point per calendar day, not per
batch) — but only call it again if there's a genuinely new pre-batch
state to capture.

**Mistake made and fixed (2026-09-21):** a same-day snapshot was frozen
*after* that day's 133-override batch had already landed, so it was
byte-for-byte identical to live. That silently broke the Δ (rank
change) column below: it compares the current view to the most recent
checkpoint, so with "most recent checkpoint" == "live", every company
showed a flat delta on the live dashboard even though real movement
existed (e.g. ProCook Group had genuinely moved baseline rank 77 → live
rank 142). The user caught this ("why can't I see the rank move in the
live dashboard?"). Fixed by deleting that snapshot file — with no
dated snapshots yet, `baseline` is once again the live view's "previous
run", so the Δ column now correctly shows real baseline→live movement.
**Never freeze a snapshot that has nothing new before it** — only do it
right before applying a batch that will actually change something, so
every frozen date is genuinely distinct from whatever "live" becomes
next.

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
news to find). Found an attributable catalyst for 18/25 (in
`data/company_news.json`); 7 came back with no clear finding
(LSC, FOI B, EVS, CMO, OGUN B, GE, FQT — no coverage in Bigdata.com,
or the news found didn't fit the direction/magnitude of the move, so
correctly left blank rather than guessed). ENXTPA:ALLUX (Installux
S.A.) was flagged "no finding" by the first research pass (no news
indexed in Bigdata.com's structured content) but the user specifically
asked about it, and an open-web search turned up the real cause: FCCE
(the Canty family's controlling holding company) announced a
simplified tender offer for Installux's minority shares at €500/share
on 28 May 2026 — a 74% premium to the 60-day VWAP, valuing the company
at €140.0M for 100% — which is exactly the baseline→live market-cap
move (+70.8%). Lesson: Bigdata.com's structured content missed this
one; French financial press (boursier.com in this case) via the open-
web search lane caught it. Worth trying open-web for other "no
finding" tickers if the user wants more filled in. To extend
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

A **"Top 150 changes (N)"** toolbar button opens a modal listing every
company that crossed the top-150 line since the same "previous
checkpoint" the Δ column uses — split into "Entered top 150" and "Left
top 150", each row showing the rank move, market cap, v6 score, and the
company's `newsNote` if one exists (`top150Movers()` /
`renderTop150Row()` in `site/template.html`). Each row is clickable and
expands the exact same rich detail panel the main table uses (score
breakdown, thesis, sparklines) — `renderDetailPanel(row, rank)` was
extracted out of the main table's row-expand logic specifically so it
could be reused here too, with its own `expandedTop150Ticker` state and
a `renderTop150ModalContent()` re-render function (event-delegated
click handler on `#top150Content`, toggle/collapse, only one row open
at a time). Disabled with no count on `baseline` (nothing precedes it
to compare to). This is genuinely different from "biggest rank movers"
— e.g. Installux (`ENXTPA:ALLUX`) moved -114 ranks (154→268) but never
appears here because it was already outside top 150 at both
checkpoints; conversely a company can
cross the line with a small absolute move if it started right at #150.

## Missing-dilution fallback policy (2026-09-21)

The user asked whether the pool might be hiding good candidates behind
missing/broken data (same class of question that found the original
dilution-gap bug). Audited the full 1000-company pool for gaps across
every scoring dimension (`revLTM`, `equity`, `avgNI`, `revGrowth`,
`mc0`, `gm`, `dilution`) — only `dilution` (15 companies) and `gm` (210,
already handled via pool-median fallback) have any gaps; everything
else is fully populated for all 1000, and no company has all 3
valuation lenses failing (`val_pts == 0`).

**Important distinction from the original dilution-gap fix**: those 84
companies (ProCook Group included) had *real* share-count data that a
parsing bug corrupted — Capital IQ uses both a blank cell and a literal
`0.0` as "not reported" for this field, and the original pipeline only
filtered blanks, not `0.0`s, so a `0.0` reading got treated as a real
data point and broke the `(last/first)-1` calculation, defaulting to
`dilution: null`. Re-parsing the raw extract with correct `0.0`
filtering recovered ProCook's real dilution (6.7%, full 12/12 marks).
**These 15 companies are different**: every one of their 10 periods is
blank or `0.0` — there's no real reading anywhere, even with correct
filtering. Not a bug; the source data genuinely doesn't exist. (Verify
with `c['dilutionDataMissing']` in `companies_1000_scored.json` - `False`
for the 84 that were fixed, `True` only for these 15.)

Until this fix, these 15 scored 0/12 on dilution (the current code's
implicit "assume the worst" default), the same worst-case treatment
prior to the ProCook fix, but here it's not recoverable by re-parsing.
The pool's *median* dilution_pts across the ~985 companies with real
data is 12.0/12 (most small/mid-caps here dilute very little), so
"assume the worst" was a real, disproportionate penalty for a data gap,
not a finding. The user chose (via AskUserQuestion): **pool-median
fallback, with a visible flag** — not the earlier GM-fallback pattern's
silent blend, because the user specifically wants this caveat visible
rather than hidden.

Implementation: `scripts/apply_dilution_fallback.py` (one-off,
re-runnable) sets `fixedPts.dilution` = pool median for the 15, adjusts
`fixedSumNoGm` accordingly, and sets `dilutionDataMissing: true` on the
company record; `resync_pool_ranks()`/`build_site.py` then re-sorts and
reassigns `rankFull` as normal. **3 companies moved into the top 150**
as a direct result: Maps S.p.A. (`BIT:MAPS`, was rank 441 → now 42),
Sto SE & Co. KGaA (`XTRA:STO3`, 583 → 94), Sabaf S.p.A. (`BIT:SAB`, 631
→ 124). The other 12 are still too far below the cutoff even with full
credit. The dashboard shows a red "● no share data" tag next to the
company name (main table meta line) and next to "Dilution" in the
detail-panel breakdown (`c.dilutionDataMissing` in
`site/template.html`), with a title tooltip explaining it's an
estimate, not a measurement — this must stay visible per the user's
explicit instruction, not be silently blended into the model like GM.

If a genuinely better source for these 15 companies' share counts ever
turns up (annual reports, another data vendor), replace the fallback
with a real computed value the same way `fix_dilution_gaps.py` did for
the original 84, and clear `dilutionDataMissing`.

## Full financial data drill-down (2026-09-21)

The user wanted to go deeper than the score breakdown when they open a
company - see all the raw underlying numbers, not just the derived
points. Added a "Full financial data ▾" toggle at the bottom of
`renderDetailPanel()` (`site/template.html`) that reveals
`renderFullFinancials(row)`: a metrics grid (market cap, equity,
revenue LTM, avg net income, ROE, P/B, revenue growth, dilution %,
gross margin, profitable/CFO+/dividend period %s, periods reported,
revenue consistency %) plus a period-by-period table of the full
`revHist`/`niHist` arrays (10 LTM snapshots each, oldest→latest, same
data the sparklines already use but as actual numbers). All of this
was already in the payload (`c.eq`, `c.revLTM`, `c.avgNI`, etc.) -
no data pipeline change needed, purely a presentation addition.

Wired via a single delegated click listener on `document.body` (added
once in `init()`), not per-row listeners - `renderDetailPanel()` is
shared by the main table (re-rendered constantly) and the Top 150
modal, so a body-level listener is the only wiring that survives both
without needing to be re-attached after every re-render.

## Corporate actions section (2026-09-21)

Investigating rank movers surfaces real reasons that have nothing to do
with organic performance - the Installux move was a **tender offer**
(FCCE/Canty family buyout of minority shares at €500/share, 28 May
2026, 74% premium), not earnings. A stock trading near/at an announced
tender price is a merger-arb situation, not a value opportunity, and
its v6 score is meaningless until the offer resolves. The user asked
for a dedicated section covering this event type broadly (tender
offers, M&A, spinoffs, other restructuring — not just the one case
found by accident).

`data/corporate_actions.json` — `{tender_offers, mergers_acquisitions,
spinoffs, other}`, each entry `{ticker, company, date, counterparty (or
spun_off_entity, or type for "other"), terms, note, source_url}` —
loaded by `load_corporate_actions()` in `scripts/build_site.py` and
embedded as `payload.corporateActions`. `site/template.html` has a
"Corporate actions (N)" toolbar button opening a modal with one section
per category (`renderCorpActionRow()`/`corpActionsTotal()`). The count
is static (computed once in `init()`, not per-render) since this data
doesn't depend on filters or the history dropdown — it's about the
company itself, not a point-in-time view of it.

**Scope decision**: the user initially asked for coverage across the
top 500 companies; given the cost of the news-note research pass (25
companies, ~205s, ~335K tokens for open-ended research), full top-500
coverage was estimated at 1-2+ hours and heavy usage — comparable to
the full 1000-company refresh the user already declined once for the
same reason. Offered three options via AskUserQuestion; user chose
**top 150 first, expand to 300/500 later if useful** — a narrower,
targeted screen (≤2 search calls per company: entity resolution + one
corporate-action-keyword search, retry on the open-web lane only if the
first comes up empty) rather than the deeper multi-angle research used
for the 25-company news-note pass. If extending coverage later, follow
the same two-call-budget discipline — a full open-ended research pass
does not scale to hundreds of companies.

**Coverage as run (2026-09-21): partial, ~124 of 150.** Bigdata.com ran
out of API credits partway through (company #125, MEDICLIN AG onward -
26 companies never screened at all: see the agent's full report for the
list). The open-web fallback step also never ran even once - every
company that came up empty on the first structured search (~45 of them)
was queued for it, but credits ran out before that phase started. Found
17 real corporate actions from the ~124 screened: 5 tender offers
(Banca Sistema, Poulaillon, Gamma Communications, InnoTec TSS, plus
Installux found earlier), 7 M&A (adesso/omni:us, dotdigital/Alia,
Multiconsult/Rejlers merger-of-equals, Dedicare, Revenio/Visionix, LNA
Santé, Jacques Bogart - the last one flagged as preliminary/unconfirmed
by the agent, worth double-checking), 0 spinoffs, 5 other (Bastide Le
Confort divestiture, YouGov strategic review, BFF Bank capital search,
ProCredit/Ecuador sale, SergeFerrari delisting from the regulated
market to Euronext Growth). **To finish this properly**: re-run the
screen for the ~26 never-reached companies (rank 125-150) plus the
open-web retry for the ~45 flagged empties, once Bigdata.com credits
are available again - don't just re-run the whole 150 from scratch.

## USA/Canada dashboard (2026-09-24)

A second market, built to reuse the Europe data coverage that FMP/Twelve
Data have but Bigdata.com (out of API credits) doesn't. Same v6 model,
same visual design, hosted alongside Europe on the same Worker:

- **Live at `/us.html`** (Europe stays at `/index.html`) — same
  `wrangler.jsonc` static-asset config serves it automatically, no Worker
  changes needed.
- **New source files**, saved under `data-us/raw/` (same pattern as
  `data/raw/Europe_15m-1B.xls`):
  - `USA_and_Canada_15m-1B.xls` — raw Capital IQ extract, 8,300 companies
    $15M–1B market cap, byte-identical 87-column layout to Europe's file.
  - `USA_Canada_SmallCap_Value_Shortlist_AllSectors.xlsx` /
    `USA_Canada_NonFinancial_Shortlist.xlsx` — two prior AI-generated
    top-150 runs (all-sector and non-financial-only cuts), used both as
    reference/sanity-check data and as ground truth for sector
    classification (see below).
  - `GM_Research_Data_USCanada.xlsx` — gross-margin research, 280
    companies (one contaminated row, NYSE:CARS, excluded — its Notes
    field contained a leaked AI-reasoning trace contradicting its own
    "as reported" source classification).
- **No prior ingestion code existed for this market** (unlike Europe,
  where universe construction happened in an earlier Claude.ai chat).
  `scripts/ingest_us_pool.py` implements the same 7 quality gates from
  the Methodology sheet in the shortlist files from scratch: fund/SPAC/
  REIT/trust name-pattern exclusion (plus an explicit
  `MutualFund:`/`Index:`/`OTCPK:PINK:` ticker-prefix exclusion, added
  after 12 mutual-fund tickers slipped past the name-pattern check),
  ≥7/10 periods track record, positive revenue every reported period,
  ≤20% dilution (missing share-count data → pool-median fallback with a
  visible flag, same policy as Europe's 15 no-data companies, not an
  exclusion), positive overall revenue growth, positive latest equity,
  ≥50% profitable periods. `scripts/us_scoring.py` reproduces the
  fixedPts formulas (dilution/revenue-growth banding matches Europe's
  validated curves exactly); `scripts/scoring.py`'s GM banding, lenses,
  and percentile ranking are reused unchanged via `scripts/build_site_us.py`.
- **Two independent scored pools, not a filter** — the "Non-financial"
  survivors are a genuinely separate universe (banks/REITs/insurance/
  asset-management companies removed *before* scoring, so percentiles
  and the v6 score itself differ from the all-sector run), toggled
  in-page via `setSector()` in `site/template_us.html`, which reassigns
  the top-level `COMPANIES`/`HISTORY`/etc. state and re-renders:
  - All sectors: **517** survivors (from 8,300 raw rows)
  - Non-financial only: **288** survivors
- **Sector classification** had no source column in the raw extract to
  key off, and name-keyword heuristics proved unreliable (22/66 known
  financials misclassified — names like "Green Dot Corporation" or
  "LendingTree, Inc." don't match bank/insurance keywords). Resolved via
  a layered reference-set approach: the two shortlist files plus the GM
  research batch (which explicitly excludes financials) cover ~342 of
  the 517 companies as ground truth; the remaining ~176 were resolved
  via FMP's `profile-symbol` sector/industry endpoint.
- **Known data gap, disclosed in the dashboard footnote**: verified
  gross margin currently covers 305/517 companies (59%) vs. Europe's
  much higher coverage. Traced (via a full field-by-field replay of
  NasdaqGS:SLP against a known reference score — every raw input matched
  exactly) to the valuation-percentile lens being computed against a
  partial-GM peer pool, not a scoring bug. Expect this market's ranks to
  drift further from any prior manual run than Europe's do, until GM
  research coverage is extended (same workflow as Europe's, see
  "Explicitly deferred" below — no refresh cycle has run for this market
  yet, so live == baseline for every company).
- `gm_overrides` for this market are still empty (no GM refresh cycle has
  run) — localStorage keys are namespaced separately from Europe's
  (`shortlist_us_mc_overrides_v1` / `shortlist_us_gm_overrides_v1`), so
  in-browser edits on the two dashboards can't collide.
- A market-cap refresh + corporate-actions screen has now run once (first
  batch, 2026-09-24) — see the dedicated section below for what's done
  and what's left.
- Cross-navigation dropdown between the two dashboard pages: **done**
  (2026-09-24) — see "Market selector dropdown" below.

## Market selector dropdown (2026-09-24)

Both `site/template.html` and `site/template_us.html` now have a small
"Market" `<select>` above the page title (`#marketSelect`, wired once in
`wireToolbar()` with a plain `window.location.href = e.target.value`
change handler — this is page navigation, not app state, so no dashboard
JS state is involved). Options today: Europe (`/`) and USA & Canada
(`/us.html`), each page pre-selecting itself. Adding a third market later
is one more `<option>` in each template plus updating the other pages'
lists to include it.

## USA/Canada market-cap refresh + corporate actions, batch 1 (2026-09-24)

First live-data pass for this market, run the same day the dashboard
itself shipped. Scope: the **union of the top-150-by-v6-score companies
in each sector view** (all-sector ∪ non-financial), 238 unique tickers —
the same "start with the shortlist, not the full pool" precedent as
Europe's market-cap refresh.

**Data sources, since Bigdata.com has no credits for this market either:**
- **FMP `profile-symbol`** for US-exchange-listed tickers (NYSE/NYSEAM/
  Nasdaq*/OTCPK) — confirmed on this session's connected plan: FMP's
  `quote` and `company` `market-cap`/`batch-market-cap` endpoints are
  gated to a higher tier (`ACCESS DENIED` even for well-known names), but
  `profile-symbol` works and returns `marketCap` directly in USD. 198 of
  the 238 priority tickers are US-exchange-listed.
- **WebSearch + live FX conversion** (`Twelve_Data: currency_conversion`)
  for the 40 Canada-only (TSX/TSXV) and UK-AIM (2 names — Somero
  Enterprises, Spectra Systems — foreign private issuers that showed up
  in the Capital IQ US/Canada screen despite their primary listing being
  London AIM) tickers FMP's plan doesn't cover at all (even `.TO`-suffixed
  Canadian symbols come back `ACCESS DENIED`).
- **WebSearch** again for the corporate-actions screen (same 1-2-search-
  per-company discipline established for Europe's screen — see "Corporate
  actions section" above).

**Hard limits hit, both confirmed independently (not just agent-reported):**
- **FMP rate limit** — `profile-symbol` started returning `Rate limit
  reached for tool "company"` after ~20 calls; confirmed still limited via
  a direct test call from the main session. No visibility into the reset
  window from the tool's own error message.
- **A session-wide WebSearch call budget (200 calls)** — shared across
  *every* concurrent subagent in the session, not per-agent. Three
  parallel corporate-actions agents plus the Canada/AIM market-cap agent
  all drew from the same pool and collectively exhausted it mid-run. This
  is a real constraint worth remembering for any future large batched
  WebSearch task in this project: **don't run more than one WebSearch-
  heavy agent at a time** (or budget ~200 total calls across however many
  you do run in parallel) — running 4 in parallel here meant none of them
  got a fair, predictable share.
- The Canada/AIM agent also tried ~15 different WebFetch domains
  (stockanalysis.com, TMX, Yahoo/Google Finance, TradingView, GuruFocus,
  MarketWatch, WSJ, etc.) as a fallback once WebSearch was exhausted —
  every one came back `EGRESS_BLOCKED` by this sandbox's network proxy.
  WebFetch is not a viable fallback for market data in this environment.

**Results — market caps: 45 of 238 refreshed** (`data-us/mc_overrides_applied.json`,
same `{ticker: {mc, source, updatedAt}}` schema as Europe's, shared across
both sector payloads since a company's real market cap doesn't depend on
which sector view you're looking at it from — wired into
`scripts/build_site_us.py`'s `load_mc_overrides()`).
- 20 via FMP (all US-exchange), 25 via WebSearch+FX (Canada/AIM).
- Sanity-checked every value against the `mc0` baseline (>5x or <0.2x
  would have been excluded as likely errors — **none were**). Six 1.5-2x+
  swings were double-checked individually: four are fully explained by
  real corporate actions found in the same batch (Beazer Homes, Avanos
  Medical, and MarineMax all trading toward pending/closed deal prices;
  ACRES Commercial Realty's *drop* is explained by a dilutive
  internalization merger that issued ~7.5M new shares) — the other two
  (AMN Healthcare +82%, Kforce +100%, Build-A-Bear -35%) were screened
  clean for corporate actions in the same pass, so treated as real,
  organic moves, not data errors — same judgment call Europe's refresh
  made for Halfords Group's +87%.
- **Remaining, saved to `data-us/mc_refresh_remaining.json`** for a clean
  resume: 178 tickers still need FMP (`fmp_remaining`), 15 still need a
  market-cap source entirely — 9 TSX + 6 TSXV names the Canada/AIM agent
  could not reach by any available tool (`websearch_remaining`).

**Results — corporate actions: 25 real events found, 161 of 238 companies
screened** (`data-us/corporate_actions.json`, same 4-category schema as
Europe's, wired into `build_site_us.py`'s `load_corporate_actions()`;
coverage bookkeeping — which 161 were actually screened vs. the 77 not
reached — saved to `data-us/corporate_actions_coverage.json` so a future
pass resumes cleanly instead of re-screening everything). Zero tender
offers, zero spinoffs found this pass. 20 M&A, 5 other/restructuring.

Deals where the *target* receives acquirer securities (not pure cash) —
flagged since these read differently from a cash buyout for a value
investor:
- **Still pending**: PSB Holdings → Bank First Corp (OTCPK:PSBQ, all-
  stock, 0.3470 BFC/share, ~80% premium, ~Q4 2026 close); Blue Ridge
  Bankshares → HomeTrust Bancshares (NYSE:HTB is the acquirer in our
  pool, all-stock, 0.086 HTB/share, not yet closed).
- **Already closed** (informational — explains a dropped-out ticker,
  not actionable): HCB Financial → Independent Bank Corp (OTCPK:HCBN /
  NasdaqGS:IBCP, mixed cash+stock); American Woodmark → MasterBrand
  (NasdaqGS:AMWD, all-stock, 5.150 shares/AMWD share); SWK Holdings →
  Runway Growth Finance (NasdaqGM:SWKH, stock-or-cash election); Victory
  Bancorp → QNB Corp (OTCPK:QNBC is the acquirer, all-stock).
- Everything else found (Beazer Homes, MarineMax, Avanos Medical, Andrew
  Peller, Gamehost, Information Services Corp, Green Dot's two-part
  breakup, Tile Shop's going-private reverse split, Vaso's subsidiary
  divestiture) is straight cash consideration.
- One unresolved situation worth a human glance: **Canada Goose
  (TSX:GOOS)** — press reports (Aug/Sept 2025) of Bain Capital weighing a
  take-private exit with verbal PE bids around $1.35-1.4B, but no signed
  definitive agreement found as of this screen. Not added as a confirmed
  corporate action, but its ~$1.09B live market cap may already be
  partly pricing in buyout speculation.
- **Remaining 77 unscreened tickers** are listed in
  `data-us/corporate_actions_coverage.json`'s `unscreened` array, split
  roughly evenly across what were three parallel batches.

**To resume this work**: the user was told the FMP rate limit and
WebSearch budget both reset "tomorrow" (i.e., after 2026-09-24) and asked
that no further attempts be made until then — wait for explicit
go-ahead before re-running. When resuming: read
`data-us/mc_refresh_remaining.json` and `data-us/corporate_actions_coverage.json`'s
`unscreened` list rather than re-deriving the target lists from scratch,
and this time **run at most one WebSearch-heavy agent at a time** (or
explicitly split a fixed ~200-call budget across however many run
together) given what happened to the four parallel agents in this batch.

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
- Completing gross-margin research for the USA/Canada pool (212 of 517
  all-sector companies still need it — see "USA/Canada dashboard" above),
  same official-filings-only workflow as Europe.
- **Finishing USA/Canada market-cap refresh batch 1**: 178 tickers still
  need FMP lookups, 15 (TSX/TSXV names FMP's plan can't reach) still need
  a market-data source entirely — see "USA/Canada market-cap refresh +
  corporate actions, batch 1" above for the exact resume files. Paused on
  the user's explicit instruction pending FMP/WebSearch limits resetting;
  needs their go-ahead before restarting.
- **Finishing USA/Canada corporate-actions screen**: 77 of 238 priority
  companies still unscreened — same section above has the exact list.
  Same pause/resume condition as the market-cap batch.
- Once both dashboards are in steady state, the same pipeline can be
  applied to further geography/market-cap datasets the user provides.
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
