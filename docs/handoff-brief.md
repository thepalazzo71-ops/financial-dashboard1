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
  10 annual LTM snapshots each - LTM-36 through LTM, offsets in QUARTERS, so one year apart, ~9 years total; see "History slots are yearly" below). **Now saved in the
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
`revHist`/`niHist` arrays (10 yearly LTM snapshots each, LTM '15→LTM '24, same
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

## USA/Canada market-cap refresh + corporate actions, batches 1-2 (2026-09-24/25)

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

**Batch 2 (2026-09-25, run on the user's explicit go-ahead the next day):**
both limits had reset overnight. Lesson from batch 1 applied this time —
ran exactly one FMP agent (no WebSearch contention with itself) plus, at
first, one WebSearch agent for the 15 remaining Canada/AIM market caps;
once that finished, launched the next WebSearch agent (corporate-actions
remainder) alone rather than in parallel. No shared-budget starvation
this round; both finished cleanly.

- **Market caps: 234 of 238 done.** FMP got 174 of its 178 (paced in
  groups of ~10 with a save between groups, per the batch-1 postmortem —
  no rate-limit errors this time); 3 of the 4 misses are `.A` share-class
  tickers (`NasdaqGS:ARTN.A`, `NasdaqGS:VLGE.A`, `OTCPK:RSKI.A`) that came
  back `ACCESS DENIED` specifically for the dotted-suffix form (a plan-
  tier restriction, not something a dash-suffix retry would fix — that
  retry path only applies to `not_found`, not `access_denied`); the 4th
  (`OTCPK:OAKC`) was a genuine `not_found`. The Canada/AIM WebSearch agent
  got all 15 remaining Canada/AIM names (`Twelve_Data`'s currency
  conversion tool wasn't available this round — needs an OAuth login this
  non-interactive session can't do — so FX was done via a plain WebSearch
  for the current rate instead: 1 USD = 1.4116 CAD as of 2026-09-25).
  These last 4 misses are recorded in `data-us/mc_refresh_remaining.json`
  as **permanently blocked on the current FMP plan tier**, not a
  pacing/rate-limit issue — don't keep re-attempting them without a plan
  upgrade or a different data source.
- Largest new swings vs. baseline, spot-checked: `NasdaqGM:ALOT` (+238%)
  and `OTCPK:MFBP` (+110%) are both fully explained by corporate actions
  found in this same pass (AstroNova's buyout, M&F Bancorp's merger);
  `NYSE:SSTK` (-73%, the single biggest swing in either batch) is
  explained by the Getty Images merger-of-equals *termination* found in
  batch 1 crashing the stock back down. `NYSE:NSP` (+125%) and
  `NYSE:KFRC` (+100%) have no corporate-action explanation (both screened
  clean) — real, organic moves per the same judgment call used for
  Halfords/BZH/HZO/ACR in batch 1, not treated as errors.
- **Corporate actions: all 238 priority companies now screened**
  (`data-us/corporate_actions_coverage.json`'s `unscreened` is empty).
  Batch 2 found 11 more real events (1 tender offer, 7 M&A, 3 other) —
  running total **36**: 1 tender offer, 27 M&A, 0 spinoffs, 8 other.
  Notable new finds: Simulations Plus (NasdaqGS:SLP) going private via
  Altaris tender offer at $18.50/share; Safety Insurance Group
  (NasdaqGS:SAFT) being acquired by MAPFRE at $105.00/share; Sun Country
  Airlines (NasdaqGS:SNCY) acquired by Allegiant in a mixed cash+stock
  deal (0.1557 Allegiant shares + $4.10 cash/share); Northrim BanCorp
  (NasdaqGS:NRIM) as an all-stock acquirer of PBCO Financial; Roots
  Corporation (TSX:ROOT) going private at C$4.10/share; MTY Food Group
  (TSX:MTY) in a contested going-private bidding war — flagged by the
  agent as needing reverification since no definitive agreement was
  confirmed as of the screening date, treat as preliminary.
- This batch is **done** — no further scheduled follow-up needed unless
  the user wants the 4 permanently-blocked market caps pursued via a
  different source, or wants coverage extended beyond the top-150-union
  priority pool (the non-financial pool is a strict subset of the
  all-sector pool, 517 unique tickers total; the 238-ticker priority pool
  covered here leaves 279 companies — all outside the top-150 in both
  sector views — never in scope for either batch).

## Shareholding data: fabrication incident + fix (2026-09-25)

The user asked for a "Shareholding" view in the company detail panel
(main shareholders, insider/officer ownership). Investigating what
already existed turned up a real data-integrity problem worth flagging
prominently for anyone continuing this project.

**What was found**: the US pool's `thesis.main_shareholders` field (from
the original US shortlist files' Investment Thesis sheet) was mostly
honest ("Not disclosed in public filings" for 190/517) but **10 entries
were fabricated** — nine unrelated companies (Stepan, XPEL, Winnebago,
Virtus, Standard Motor Products, Insteel, HealthStream, Universal
Logistics, and Crown Crafts) all
carried the identical invented figures "BlackRock (10.6%), Donald Smith
& Co. (9.2%), T. Rowe Price Investment Management (7.0%)" — not
plausible for nine unrelated companies. A tenth (TSX:BNE, Bonterra
Energy) cited "Allegiant Travel DEF 14A example not Bonterra-specific"
as its own source — a self-admitted placeholder used for the wrong
company. **Europe's equivalent data was checked and is clean** (zero
duplicate values across 136 real entries) — this was a US-only problem.

**Immediate fix**: purged all 10 fabricated `main_shareholders` values
to `null` before building any UI on top of them.

**UI added** (both dashboards, `renderDetailPanel()` in both templates):
a new "Shareholding" section in the detail panel's left column (grouped
with business description/competitive position, not buried among the
financial sparklines like the old placement), showing main shareholders
and a new `insider_ownership` field. Also fixed a real bug in the same
area: these prose fields carry their source citation inline as markdown
`([label](url))`, which was never being converted to an actual clickable
link — even the genuine citations rendered as inert bracket text. Added
`mdLinksToHtml()` to fix this at render time.

**Insider-ownership data source**: checked `mcp__FMP__insiderTrades` and
`mcp__FMP__form13F` first (user's stated preference, to minimize
hallucination risk with structured SEC data) — both are **fully gated**
on this plan tier, not just for certain symbols (`ACCESS DENIED` on every
call, whole-tool level). WebSearch was the only viable source, so this
research got extra explicit anti-fabrication discipline given it's the
exact failure mode that caused the incident: every entry needs a real
per-company citation, "not disclosed"/null is always an honest fallback,
and watching for the same institution+percentage combo recurring across
companies (the actual smoking gun that caught the original problem).

**Wave 1 (2026-09-25)**: researched 195 of the 243-company target list
(10 previously-fabricated companies first, then the rest of the
238-ticker US priority pool by rank) before hitting the shared 200-call
WebSearch budget. Added 122 unique companies' main shareholders and 121
unique companies' insider ownership (each counted once per sector-pool
file they appear in — see the commit for exact per-file counts); cleared
60 stale/boilerplate values that weren't re-verified this round rather
than leave them unreviewed. All 10 previously-fabricated companies now
have fresh, cited, ticker-specific data (or an honest null) — spot-
checked independently for the same duplicate-figure pattern; found none.
Data-quality notes from the research agent worth knowing: a handful of
entries use 10-20-year-old proxy data, explicitly caveated as
"(dated data)" in the text rather than presented as current (anything
older than ~20 years was dropped to null instead); Pro-Dex
(NasdaqCM:PDEX) had a self-contradicting source (insiders 94.1% +
institutions 16.2% summing over 100%) and was left null rather than
guessed; Silvercrest (NasdaqGM:SAMG) had two conflicting insider-%
snippets (12.3% vs "under 1%") and was also left null.

**Remaining work** (`data-us/shareholding_research_remaining.json` has
the exact resume list): 48 US priority-pool tickers unprocessed (one,
OTCPK:MVLY, was accidentally skipped mid-batch despite falling before
the budget cutoff — resume there first), plus Europe's existing 150
thesis companies still need `insider_ownership` added (their
`main_shareholders` was already clean and is untouched). Same one-
WebSearch-agent-at-a-time discipline as the market-cap/corporate-actions
batches applies here too.

## Coverage extension round, both markets (2026-09-29)

A big round of follow-up work, all on the user's explicit go-ahead
batch-by-batch. Order matters here since it explains some cross-market
back-and-forth: shareholding wave 2 (US) → US market-cap next tier →
Europe market-cap next tier → Europe insider-ownership → Europe
market-cap tiers 2 and 3 → **user caught a real gap this surfaced**
(Mercor/mcr S.A.'s divestiture wasn't in corporate actions since it's
rank 222, outside the original top-150 screen) → Europe corporate-actions
screen extended to match.

**US shareholding wave 2**: finished the 48 remaining US priority-pool
tickers from wave 1's resume list (see "Shareholding data" above) —
38/48 got both fields, 5 got one, 5 came back honest nulls. Independently
re-verified (not just trusting the agent) for the fabrication pattern
that started this whole thread: zero duplicates across all 243 companies
researched across both waves. **US shareholding is done.**

**US market-cap next tier**: +48 companies via FMP (the next tier by
rank, just below the 238-ticker priority pool) — 272/517 now refreshed.
2 Canada-only (TSX) tickers in that tier deferred (`data-us/mc_next_tier_deferred.json`).

**Europe market-cap tiers 151-300**: three batches of 50 via WebSearch
(Bigdata.com still out of credits, FMP has zero non-US coverage,
Twelve_Data unavailable — same constraints as before). 173 → 216 → 259
of the 1,000-pool now refreshed. One deliberate sanity-check override:
Maisons du Monde (ENXTPA:MDM) landed at 0.19x baseline, just under the
auto-exclude threshold, but multiple sources corroborate a genuine ~85%
stock collapse from a June 2026 debt-restructuring settlement — kept,
not excluded (this also reconciles an *earlier* exclusion of the same
company from months ago as "implausible"; it looks like that earlier low
price was real after all). One batch's final handback message hit an
API session rate limit ("You've hit your session limit"), separate from
the WebSearch budget — but the agent's actual work (all 50 results,
merge-saved incrementally) was already complete and intact; verified the
output file before merging rather than re-running.

**Europe insider-ownership research**: added `thesis.insider_ownership`
for 112 of the existing 150 thesis companies (38 honest nulls) via
WebSearch, same discipline as the US waves — main_shareholders was
already clean and untouched. Independently re-verified: zero duplicates,
zero reused figures.

**The gap this surfaced**: the user asked about WSE:MCR (mcr S.A.,
formerly Mercor) after noticing its ~53% market-cap drop in the ranks
251-300 batch, and asked whether it was a spinoff and whether corporate
actions caught it. It hadn't — Mercor sits at rank 222, outside the
top-150 the original corporate-actions screen covered. Investigated:
not a spinoff, a **divestiture** — Mercor sold its fire-ventilation/
smoke-extraction business to Kingspan Group (up to PLN 420M, closed
~Oct 2025), rebranded to "mcr Spolka Akcyjna", and paid an outsized
special dividend from the proceeds. Added to `data/corporate_actions.json`
under "other". This is exactly the kind of gap that motivates keeping
corporate-actions coverage in sync with market-cap coverage, not letting
one race ahead of the other.

**Europe corporate-actions screen extended to ranks 151-300**: three
batches of 50 (matching the market-cap tiers), 29 real events found
total across all three parts (46 total corporate actions on file now, up
from 17). Highlights: Surteco Group SE's mandatory takeover offer
(rejected by the majority pool) combined with an active plan to divest
major business lines — structurally the closest analog to the Mercor
case found; Maisons du Monde's distressed debt-for-equity
recapitalization (Alteri/Eicos took ~95% of capital, court-validated
July 2026 — this is the SAME company whose market-cap swing was flagged
above, now with the full explanation on file); Criteo S.A.'s Vista
Equity/Quinti Capital take-private bid (~$3.7B), preceded by a
France-to-Luxembourg re-domiciliation apparently done to enable the deal
structure; International Personal Finance's essentially-complete
BasePoint Capital acquisition. Judgment calls preserved rather than
guessed at: denied/unconfirmed rumors excluded (Pets at Home takeover
speculation, explicitly denied by BC Partners); stale events excluded
(Close Brothers' CBAM divestiture, completed Feb 2025, outside the
~12-18 month lookback); cosmetic-only renames excluded (PageGroup →
Michael Page plc). One duplicate correctly deduplicated across batches
(mcr S.A. was independently re-found in part 2, already on file from the
direct add).

**Result**: both Europe's market-cap coverage (259/1,000) and its
corporate-actions screen (ranks 1-300) now extend to the same boundary
— the lesson from the Mercor gap, applied.

## US corporate-actions screen extension + Europe qualitative thesis extension (2026-09-29/10-01)

Two more pieces of the "keep coverage in sync" pattern from the round
above, both prompted by the user's own observations rather than planned
in advance.

**US corporate-actions screen extended to match market-cap coverage**:
the same class of gap as the Mercor case, just on the US side - US
market-cap coverage had grown to 272 companies while corporate-actions
screening still only covered the original 238-ticker priority pool.
Screened the 38-company gap via WebSearch; found 6 real events,
including a direct analog to Mercor: Tompkins Financial Corporation sold
its wholly-owned insurance subsidiary to Arthur J. Gallagher & Co. for
~$223M cash. US corporate actions now total 42 (up from 36), and
coverage (276 tickers screened) matches market-cap coverage (272
refreshed).

**Europe qualitative thesis research extended to ranks 151-300**: the
user asked why Admicom Oyj was the dashboard's biggest mover and noted
it had no qualitative data - investigating turned up that 130 of the 150
companies now ranking 151-300 had never gotten the original top-150
deep-dive (business description, competitive position, main
shareholders, insider ownership, red flags, website), because that
research was a one-time pass against the original baseline ranking, not
something that keeps pace as market-cap refreshes reshuffle ranks. The
user then explicitly asked to "run the qualitative on all the new 150
entrants."

Scope clarification worth remembering: "ranks 151-300 by current rank"
and "new entrants to the top-150" are NOT the same set. Admicom itself
(the company that prompted this whole thread) currently ranks #79 -
*inside* the top-150 - so it fell outside the 150-company ranks-151-300
batch and had to be added as a direct, individual addition alongside one
other true top-150 entrant lacking thesis, Graines Voltz S.A. (whose
research surfaced a real, dated 2017 minority-shareholder governance
dispute with the ~70%-controlling Voltz family - relevant context for
its persistently low valuation, explicitly framed as historical, not
current).

Research for the 130-company ranks-151-300 tier ran in 3 batches of
~44 via WebSearch (business_description, competitive_position,
main_shareholders, insider_ownership, red_flags, website per company),
same anti-fabrication discipline as every prior research wave - every
batch was independently re-verified (not just trusting the agent's
self-report) for exact-duplicate values and reused shareholder
name+percentage combos before merging; found none across all 130+2
companies. One batch's agent hit a session-wide API rate limit (distinct
from the WebSearch-call budget seen earlier) partway through its own
final report-generation step, but had already completed 30 of 42
companies with all results merge-saved - verified the output file
directly and ran a small 12-company follow-up for the remainder rather
than re-running the whole batch from scratch. This mirrors the earlier
pattern where a market-cap batch's agent "failed" on the same kind of
session-limit error but its actual work was already complete and
intact - **always check the output file before assuming a failed/rate-
limited agent lost its progress.**

**Result**: every company currently ranking in Europe's top 300 now has
full qualitative research on file, not just the original top 150.

## Corporate-actions click-to-expand + tier-4 market-cap batch, both markets (2026-10-01)

**Corporate actions modal is now click-to-expand**: each row inside the
"Corporate actions" modal (both dashboards) resolves its ticker to the
current scored pool and, on click, expands the same shared
`renderDetailPanel()` used by the main table, Top-150-changes modal, and
Biggest-movers modal — score breakdown, business description,
shareholding, financials, all inline. Same click-to-expand/row-wrap/state-
toggle scaffolding as the two prior modals, just pointed at a ticker
lookup (`findScoredRowAndRank`) instead of a precomputed row. Verified via
Playwright on both dashboards (real `.click()`, not just JS state
injection) before committing.

**Tier-4 market-cap batch** (next ~50-company tier for both markets,
continuing the established per-tier pattern):
- Europe (ranks 301-350, WebSearch-only — Bigdata.com remains out of
  credits, FMP has no non-US coverage): 50/50 resolved cleanly, no
  auto-exclude-threshold flags. Europe mc coverage: 259 → 304 of 1000.
- US (next 48 FMP-eligible tickers beyond existing coverage): 44 of 48
  resolved (3 `.A`-share-class tickers access-denied, 1 not found).
  **Excluded OTCPK:HBIA (Hills Bancorporation) from the merge**: FMP
  returned a $3.27B market cap vs. a $745M baseline (~4.4x) — under the
  project's 5x auto-exclude threshold but flagged by the agent itself as
  an outlier. Independent WebSearch verification found Hills Bancorp has
  ~8.9M shares outstanding and a real market cap of $650-865M across
  Investing.com/CNBC/Yahoo/SimplyWall.st — confirming the FMP figure was
  bad data (likely a share-count mismatch on FMP's side) and the
  $745M baseline was already correct. Left it unmerged rather than
  overwrite good data with bad. Merged the other 43. US mc coverage:
  272 → 315 of 517.

Both markets' corporate-actions screening and (for Europe) qualitative
thesis research now trail the new market-cap frontier by one tier
(ranks 301-350 Europe / tickers 316-363-ish US aren't yet screened) —
not yet requested, flagged under "Explicitly deferred" below.

## Tier-5 market-cap batch, both markets (2026-10-01)

Same pattern, next ~50-company tier, run immediately after tier-4 per
explicit "do the next tier of both" request. One change this round: US
target generation switched from a straight rank-window slice to
filter-out-already-covered-then-take-next-50 (mirroring the method
already used for US), after tier-5's initial Europe window turned up
3 tickers that had already been covered — re-ranking after each merge
shuffles rank order enough that a fixed window can overlap previous
coverage.

- **Europe**: 50/50 resolved via WebSearch, no auto-exclude flags.
  A few names had source disagreement (Delta Plus Group, Atlantic
  Insurance, Hermle AG - merged with the agent's best estimate) or
  dated (May-July 2026) quotes - worth rechecking on a future refresh,
  not urgent. Two flagged swings were corroborated by specific news
  (EXEL Industries down ~47% trailing year; Swiss Water Decaf up ~80%
  on a same-day surge headline) and kept as-is. Coverage: 304 → 354 of
  1000.
- **US**: 43 FMP-eligible tickers, 42 resolved, 1 not found
  (OTCPK:OAKC — not in FMP's database at all, not yet researched any
  other way). **OTCPK:HBIA (Hills Bancorporation) recurred** with the
  *exact same* $3.27B/4.39x anomaly as tier-4 (identical stale $46.76
  price both times) — expected, since excluding it from a merge rather
  than fixing it just means it resurfaces every time a target-list
  generator re-selects "not yet covered" tickers. Resolved permanently
  this time: merged a corrected value ($732.96M, consistent with the
  $745.2M baseline) sourced independently via WebSearch
  (stockanalysis.com), tagged with a source note explaining FMP's data
  is bad for this thinly-traded OTC name. Coverage: 315 → 357 of 517.
- **Canada**: FMP doesn't resolve TSX/TSXV tickers, so the 7 Canadian
  names due for this tier were folded into the Europe WebSearch batch
  rather than run as a separate agent (same WebSearch budget either
  way). All 7 resolved cleanly; two (AGF.B, VCM) had moderate source
  spread and were merged with a mid-range estimate. Coverage (within
  the combined 364): 357 → 364 of 517.

**Lesson for future HBIA-like cases**: when an agent flags a specific
ticker as a likely data-quality outlier under the auto-exclude
threshold, resolve it with a corrected value in the same round rather
than just excluding it — an override-less "not yet covered" ticker will
keep getting re-selected into every subsequent tier's target list and
re-flagged, wasting a research call each time.

## Net Debt box + corporate-actions/thesis catch-up to tier-5 (2026-10-01)

**Net Debt box added to the full financial data drill-down** (both
dashboards): the user asked for it, but net debt (or cash/total debt)
was never part of either pool's source data extract, unlike market cap
which at least started with a baseline. Rather than launch a large
research project unprompted, asked the user how to scope it - they
chose to add the UI slot now (`c.netDebt`, wired through both build
scripts, shows "no data yet") and populate it later via the same
incremental research pattern already used for gross margin. No company
currently has a value; this is pure plumbing for future research.

**Corporate-actions and Europe thesis research caught up to the tier-5
market-cap frontier** (the gap flagged in the previous handoff entry):

- **Europe corporate-actions**: 54-company gap (tickers mc-covered but
  outside the previously-screened top-300-by-rank) screened via
  WebSearch. 8 new real events found (2 of the agent's 10 raw findings -
  Criteo, Advanced Medical Solutions - turned out to be re-discoveries
  of events already on file, caught by a **ticker-based** dedup pass;
  a source-URL-based check missed them since each was reported by a
  different article). Also added `data/corporate_actions_coverage.json`
  (mirroring the US pool's existing file) to track exactly which
  tickers have been through a screening pass, so future rounds can
  compute the gap precisely instead of approximating by rank window.
  Coverage: 300 → 354.
- **US corporate-actions**: 89-company gap, split into two 45/44
  WebSearch batches (sequential, since corporate-actions screening is
  WebSearch-only for both markets). 23 new events total - mostly bank
  M&A (community bank consolidation is clearly active in this part of
  the pool), plus Guardian Capital Group taken private by Desjardins
  and Varex Imaging acquired by Teledyne. Both agents proactively
  caught and excluded several name-collision traps (similarly-named
  banks with unrelated real events). Coverage: 276 → 365 of 364
  mc-covered (one ticker screened but no longer mc-covered after a rank
  shuffle - expected and harmless).
- **Europe qualitative thesis research**: 72-company gap (top-354-by-
  rank companies with no thesis on file), split into two 36-company
  WebSearch batches. The first attempt at part 1 hit a session-wide API
  rate limit almost immediately (empty output, nothing saved - unlike
  the "already got most of the way through" pattern seen in earlier
  rate-limit incidents this session); retried after the stated reset
  time and it completed cleanly. Both parts independently re-verified
  for duplicated/reused shareholder name+percentage combinations before
  merging (none found, in either part alone or across both together).
  Surfaced several notable items for investor awareness: Kraš d.d. is
  mid-squeeze-out and likely to delist, Eurofins-Cerep is ~96%
  owned by its parent (thin free float), VIB Vermögen's majority owner
  pushed through a control/profit-transfer agreement after an earlier
  related-party-loan dispute, Lion Capital has a live minority-
  shareholder governance dispute, BFF Bank had a 2024 Bank of Italy
  probe and dividend suspension, and Mutares was the subject of a 2024
  short-seller report it disputes. Result: every company in Europe's
  top 354 now has full qualitative research on file.

## US/Canada qualitative thesis research project (2026-10-01)

User noticed Saul Centers, Inc. (NYSE:BFS) had no qualitative data and
asked if that was normal - it was: the US dashboard's "thesis" concept
(business description, competitive position, shareholders, insider
ownership, red flags, website) had only ever been researched for the
original ~243-company priority pool from the initial shortlist files,
never extended as market-cap coverage grew to 364 of 517 the way
Europe's was. User asked to close that gap for all mc-covered
companies.

**Found and fixed a real data-quality bug mid-project**: the initial
gap computation (`mc-covered AND NOT hasThesis`) returned 179
companies, but the first research batch's merge step (which always
defensively checks `if c.get('thesis')` before writing, never
overwriting existing data) found that 16 of its 36 targets already had
real thesis content despite `hasThesis: false` - a stale/wrong flag
that predated this project (confirmed via git history on an untouched
commit). A full sweep fixed the flag everywhere it was wrong: 66
companies in `companies_pool_all.json`, 35 in
`companies_pool_nonfinancial.json`. This cut the true remaining gap
from 179 to 72 after parts 1-2 (which had already been generated from
the stale list and launched before the bug was caught - their
redundant targets just no-op'd harmlessly at merge time, no data was
lost or duplicated). Parts 3-4 were generated from the corrected gap
and needed no further correction.

Ran as 4 WebSearch batches of 36 companies each (144 total dispatched,
~107 genuinely new after dedup overlap from parts 1-2's stale targets).
**Both `companies_pool_all.json` and `companies_pool_nonfinancial.json`
had to be updated for every ticker** - the non-financial pool is a full
288-ticker subset of the 517-ticker all-sector pool, stored as a
separate duplicate JSON array, not a derived view, so a company's
thesis has to be written to both files or the non-financial sector view
goes stale. Every batch independently re-verified against the full
existing dataset (not just its own batch) for duplicated shareholder
name+percentage combinations before merging. Two recurring "matches"
surfaced across multiple batches and were judged benign after
inspection rather than excluded: a generic boilerplate phrase ("insiders
own under 1%") the regex check mistook for a name, and Dimensional Fund
Advisors LP appearing at a similar ~6% stake in two unrelated
companies (The Eastern Company, Riverview Bancorp) - normal for a
$600B+ index manager with small positions across thousands of
small-caps, confirmed benign because each citation pointed to its own
distinct, specific source URL.

**Result**: thesis coverage went from a reported 216/517 (actually
already higher before the flag fix) to 395/517, with all 364
mc-covered companies now covered - matching Europe's pattern of
keeping qualitative research in sync with market-cap coverage. Notable
items surfaced worth investor attention: several companies are
mid-acquisition and their standalone thesis is arguably moot (United
Security Bancshares, Pacific Financial Corp, National Capital Bancorp,
Diamond Hill Investment Group - already closed), Urbanfund Corp has a
live related-party-loan red flag (a $10M loan to its own controlling
shareholder's construction company), Monro has an active activist/
poison-pill situation (Icahn ~16-17%), and Knight Therapeutics has a
documented governance dispute over founder conflicts of interest. Full
list of per-batch findings is in the four commit messages for this
project (2026-10-01, "US qualitative thesis research part N/4").

**Lesson for future similar projects**: always trust the merge script's
defensive "don't overwrite existing data" check over an upstream gap
computation that depends on a flag field - a flag can drift from the
content it's supposed to describe, but checking the content directly
at write-time catches that drift before it causes damage, and is worth
doing at write time even when the gap list was supposedly pre-filtered.

## Tier-6 market-cap batch, both markets (2026-10-05)

Next ~50-company tier for both markets, same pattern as every prior
round.

- **Europe**: 50/50 resolved via WebSearch, no auto-exclude flags.
  Several swings (LU-VE Group +77%, LEM Holding +86%, Cascades +55%)
  had no corroborating news in the research agent's own search despite
  staying under the 5x threshold - independently re-verified via
  WebSearch before merging rather than accepted on the agent's say-so:
  all three are real (LU-VE has a record H1 2026 and a €100M
  hyperscaler data-center-cooling contract; LEM Holding is trading near
  its 52-week high; Cascades got three broker price-target raises after
  a strong Q2). Coverage: 354 → 404 of 1000.
- **US**: 43 FMP-eligible tickers, 42 resolved, 1 not found (OTCPK:OAKC
  - still not in FMP's database, same as every prior round; needs a
  WebSearch follow-up outside this batch's scope if it's ever worth
  revisiting). Three severe outlier ratios (Cable One ~0.10x, Mercer
  International ~0.17x, America's Car-Mart ~0.08x vs baseline) -
  independently verified via WebSearch rather than assumed to be FMP
  data errors: all three are real, multi-source-corroborated crashes
  (Cable One collapsed from a 52-week high of $180 to ~$11-13; Mercer
  International is down ~69% over 3 years to ~$0.25/share; America's
  Car-Mart is down ~96% YoY to ~$1/share - all three independently
  confirmed across stockanalysis.com, CNN, and wallstreetzen). Coverage:
  364 → 406 of 517.
- **Canada**: the usual 7 TSX tickers FMP can't resolve, folded into the
  Europe WebSearch batch. All 7 resolved cleanly. Combined US/Canada
  coverage: 406 → 413 of 517.

Corporate-actions screening and Europe's qualitative thesis research
now trail this new frontier by one tier again - same "extend coverage
to match" follow-up as every prior round, not yet requested for tier 6.

## Tier-6 corporate-actions/thesis catch-up + US partial-thesis backfill (2026-10-05/06)

**Four-batch catch-up to the tier-6 market-cap frontier**, same pattern
as the tier-5 round:
- Europe corporate actions (50-company gap): 8 new events found via
  WebSearch - Infas Holding/Ipsos, MHP SE's Greek poultry acquisition,
  Brødrene A&O Johansen/Elektroimportøren, SThree's rejected unsolicited
  approach (offer period still open), Spire Healthcare's £1.03bn
  take-private, Altri SGPS's AeoniQ/Greenalia stakes, Quercus TFI's
  merger with Templeton Asset Management Poland, and Aspo Oyj's ESL
  Shipping demerger. Coverage: 354 → 404.
- US corporate actions (49-company gap): 11 new events - Crown Crafts
  tender offer, Cable One's $1.3B Mega Broadband buy-in (likely
  relevant context for its recent crash - added leverage), Mistras
  Group/H.I.G. Capital, Clarke Inc/Ravelin Properties REIT, Friedman
  Industries, two separate bank-merger targets (Morris State, Ottawa
  Bancorp), Cross Country Healthcare/Knox Lane, plus three "other"
  situations: Perma-Pipe's concluded strategic-alternatives review
  (staying independent), America's Car-Mart's special committee amid
  financial distress, and Cascades' packaging-segment exit. Coverage:
  276 → 414 (of 413 mc-covered - one ticker drifted off mc-coverage
  after a rank shuffle, expected/harmless).
- Europe thesis research (52-company gap): ran in two parts after the
  first agent hit a session-wide rate limit at 42/52 (confirmed via
  the output file - no progress lost, resumed with the remaining 10).
  Flagged governance-concentration items: Brd. Klee A/S (~90-97.6%
  controlled by Fritz H. Schur entities), IMC S.A. (~76% held by
  Agrovalley Ltd., plus acute Ukraine war/occupied-farmland risk in its
  financials), Boreo Oyj (~70-71% Preato Capital), K. Kythreotis
  Holdings (founder is both Chairman and CEO at ~53.6%). Result: every
  company in Europe's top 404 (by current rank - the correct scope,
  since mc_overrides membership drifts slightly from top-N-by-rank
  after each merge) now has full qualitative research.
- US thesis research (34-company gap): flagged several companies for
  shortlist-hygiene review (not acted on - per policy, no manual
  ranked-list edits): Cross Country Healthcare and Morris State
  Bancshares are both mid/already-merger, America's Car-Mart has
  going-concern warnings and ~1/3 of its dealerships closing. Agent
  caught two aggregator data-quality artifacts and excluded them rather
  than reporting as fact (a bogus "44% insider stake" at BJ's
  Restaurants; a CEVA Inc. figure that actually traced to an
  institutional 13G stake, not insider ownership).

**US partial-thesis backfill (66 companies, user-initiated)**: the user
asked why Tile Shop Holdings (OTCPK:TTSH) showed no visible qualitative
data. Investigation found it wasn't actually empty - it had real
`main_shareholders`/`insider_ownership` data from an early-project
"shareholding research" phase that predated the full 6-field thesis
concept, so `hasThesis` was (correctly) `true` and it never surfaced in
later gap-detection, but the panel showed blank/placeholder values for
business description, competitive position, red flags, and website,
which reads as "no research" even though it technically wasn't empty.
Found 66 companies total in this exact partial state. User confirmed:
backfill all 66. Ran as two 33-company WebSearch batches, each scoped
to ONLY the 4 missing fields - the existing shareholding data was left
untouched. Result: zero partial-thesis companies remain; every company
with any thesis data now has the complete 6-field set.

Notable items surfaced across the backfill: Tile Shop Holdings itself
has a documented 2013 related-party-supplier scandal (undisclosed
CEO brother-in-law-controlled COGS supplier) that led to two
shareholder-litigation settlements ($9.5M in 2017, $12M in 2020) -
directly relevant context now that its thesis panel is complete.
Several companies are already-closed or pending mergers (CBB Bancorp,
Affinity Bancshares, HCB Financial already closed; PSB Holdings, M&F
Bancorp, FONAR Corp pending - FONAR's going-private is led by the
founder's son with active Delaware Chancery litigation over price
fairness). Sylogist has a live board-control proxy fight; Franklin
Covey faces fresh securities-fraud investigations after a guidance cut.

**Lesson for future similar gaps**: a company having *some* data in a
tracking field (like `thesis` or `hasThesis`) doesn't mean it has
*complete* data - this project has now hit that pattern twice (the
hasThesis flag/content mismatch in the tier-5 round, and this
field-level partial-completeness gap in tier-6). When auditing
coverage, check for the specific fields a complete record should have,
not just whether the parent field is truthy.

## Systemic dividend-consistency bug fix (2026-10-08)

User asked why Judges Scientific plc (AIM:JDG) - a well-known UK
founder-led compounder (CEO David Cicurel, ~9.3% stake) with an
unbroken, growing real dividend since at least 2016 - scored 0/4 on
dividend consistency. Investigating surfaced a systemic bug affecting
**both pools in their entirety**: 970 of 1000 Europe companies and all
517 US companies showed `divPct: 0.0`, i.e. the model treated nearly
every company as if it had never paid a single dividend across any of
its 10 tracked periods.

**Root cause**: Capital IQ reports "Total Dividends Paid" in cash-flow-
statement sign convention - a real payment is a NEGATIVE number (cash
outflow); exactly `0.0` means no dividend that period. Verified
directly against both raw `.xls` files (e.g. JDG's raw values are
`[-3.13, -0.79, -2.3, ..., -8.91]` - all negative, all real payments).
The original ingestion counted a period as "dividend paid" using
`v > 0`, which a negative number can never satisfy - so `divPct` came
out ~0 regardless of actual history, for virtually every company in
both pools.

**Fix**: re-derived `divPct` directly from each raw `.xls` file for
every company in both pools, using the correct `v < 0` condition, and
updated the dependent `fixedPts.dividend_consistency`/`fixedSumNoGm`
fields to match. 933 of 1000 Europe companies and 371+192 of the two US
pool files changed (the untouched ones were genuine non-payers,
correctly still 0.0). Also fixed the root bug in
`scripts/ingest_us_pool.py`'s `pct_positive_of_n()` so a future
re-ingestion doesn't reintroduce it - Europe's ingestion predates this
repo (done in a prior Claude.ai chat session), so there's no equivalent
script to fix there, but the correction script covered its current data
directly from the raw file.

**Impact on the Europe shortlist**: reshuffled the actual top-150 - 15
companies entered, 15 left. Every exit still gained score from the fix
(dividends never hurt), but gained *less* than the companies that
leapfrogged them: exits are mostly partial/irregular payers (divPct
0.1-0.57) or genuine non-payers (Hvidbjerg Bank, Fast Ejendom Danmark,
Slatinska Banka, Kambi Group), while every entrant is a strong,
consistent payer (divPct 0.80-1.00) - e.g. FDM Group, GlobalData,
Pets at Home, Tokmanni Group, Braime Group. A clean, model-consistent
reshuffle, not noise.

Judges Scientific itself had already been one-off-corrected to
divPct=1.0 moments before this systemic fix was found (same Card
Factory-style precedent, verified via its real dividend history on
dividendmax.com/Fidelity/ADVFN) - the systemic fix confirmed that value
independently and is now the permanent source of truth; the one-off
edit is superseded, not stacked.

**Lesson**: when a scoring dimension looks suspiciously uniform across
a large sample (here, near-100% zeros), check the raw source data
directly rather than assuming the model's inputs are correct and
accepting it as "most companies just don't do X." A one-company fix
request (Judges Scientific) was the entry point to finding a bug
affecting literally every company in both pools.

## Tier-7/tier-8 market-cap round, both markets (2026-10-06/08)

Two more ~50-company tiers, same pattern as every round so far, with
one real wrinkle: the first Europe+Canada agent for tier-7 hit a
session-wide rate limit partway through (32 of 57 saved before the
cutoff - confirmed via the output file, no progress lost) and was
finished with a 25-company follow-up batch.

- **Europe tier 7**: 50/50 resolved via WebSearch across two runs, no
  auto-exclude flags. One coincidental duplicate mc value ($89.4M for
  both Michelmersh Brick Holdings and ECO Animal Health) verified
  benign - different sources, different raw local-currency values.
  Coverage: 404 → 454 of 1000.
- **US tier 7**: 42 of 43 FMP-eligible tickers resolved (1 not found:
  OTCPK:OAKC, no FMP coverage at all). Largest divergence (Methode
  Electronics, ~3.0x vs baseline) independently verified via WebSearch
  across gurufocus/wallstreetzen - real, not a data error. Coverage:
  413 → 455 of 517.
- **US tier 8**: 34 of 36 FMP-eligible tickers resolved. OTCPK:OAKC
  (Oakworth Capital) showed up as not_found *again* - same recurring
  pattern flagged earlier for HBIA: a ticker that's never successfully
  resolved stays out of `mc_overrides`, so every subsequent tier's
  "not yet covered" target-list filter keeps re-selecting it. One
  access_denied (TPEX:4971 IntelliEPI - FMP resolved the correct
  Taipei Exchange symbol but foreign-exchange profile data is gated
  above this plan tier). Two symbol-format quirks handled (Crawford &
  Company's real FMP symbol is "CRD-B", hyphenated, not the usual
  dot-dropping convention). Coverage: 455 → 489 of 517.
- **Canada tiers 7+8**: 7 + 14 = 21 TSX/TSXV tickers via WebSearch,
  folded into the Europe batches each round. 20 of 21 resolved; TSX:ECN
  (ECN Capital) was taken private by a Warburg Pincus-led group in
  April 2026 and no longer trades - flagged rather than removed, per
  the no-manual-edits policy. Final combined US/Canada coverage: 502 of
  517.

Remaining uncovered in the US/Canada pool at the time (2 tickers,
documented reasons): OTCPK:OAKC (no FMP coverage), TPEX:4971 IntelliEPI
(plan-gated foreign exchange data). TSX:ECN was later dropped from the
pool entirely (see "Dropped delisted/wound-down companies" below)
rather than carried as a permanent gap.

Corporate-actions screening and both markets' thesis research now
trail this new tier-7/8 frontier - not yet requested for this round.

## Tier-8 corporate-actions/thesis catch-up (2026-10-08)

Full four-batch catch-up to the tier-8 market-cap frontier, run as 7
sequential WebSearch agents (corp-actions for both markets, thesis
research for both markets split into 2 parts each given volume -
274 companies total).

- **Europe corporate actions** (50-company gap): 10 new events -
  4 tender offers (Transilvania Broker, Roularta Media's De Nolf
  family tendering for the free float to delist after 27 years,
  Nilörngruppen/Trimco-Brookfield, H&R KGaA's controlling shareholder
  stating intent to pursue delisting/squeeze-out next), 3 M&A (HSBC
  selling its Malta stake with a mandatory minority tender to follow,
  Séché Environnement as acquirer, Berentzen-Gruppe taken over by
  Sazerac at a ~68% premium), 3 "other" (LSI Software's draft
  delisting resolutions, Gerresheimer flagged as an ongoing
  takeover-interest situation despite no completed deal, OVB
  Holding's indirect change of control via the Helvetia/Baloise
  merger). Coverage: 404 → 454.
- **US corporate actions** (89-company gap, 2 parts): 34 new events
  total - notable ones include Golden Entertainment's go-private,
  Great Lakes Dredge & Dock taken private, Flushing Financial merged
  into OceanFirst (ticker retired), TruBridge taken private, a
  contested UWM Holdings/Two Harbors bidding war (unresolved),
  Forward Air's unresolved activist-driven sale process, and Canfor's
  squeeze-out of Canfor Pulp minorities. Coverage: 276 → 503 of 502
  mc-covered (one ticker drifted off coverage after a rank shuffle -
  harmless).
- **Europe thesis research** (62-company gap, 2 parts): flagged
  several active/pending M&A situations (HSBC Bank Malta's competing
  bidders, Spire Healthcare's recommended take-private, Roularta's
  delisting tender, a contested Alternative Income REIT situation) and
  real red flags (Luceco's 2017/2018 accounting restatement, Practic
  S.A.'s voluntary-delisting process with squeeze-out risk, WASGAU's
  Bundeskartellamt review, Astarta's ongoing Ukraine war exposure).
  Result: every company in Europe's top 454 (by current rank) now has
  full qualitative research - **both markets' corp-actions screening
  and Europe's thesis research are now fully caught up.**
- **US thesis research** (73-company gap, 2 parts): flagged three
  tickers for shortlist-hygiene review (not acted on, per policy):
  TSX:AGTF was taken private back in 2019 and hasn't traded in ~7
  years; Golden Entertainment and Flushing Financial (also just
  confirmed via the corp-actions batch above) likely no longer trade
  independently. OTCPK:HRGG (Heritage NOLA Bancorp) is effectively a
  wind-down/liquidation, not a going concern - flagged explicitly
  rather than given a normal thesis. Real governance disputes
  surfaced: American Vanguard's 2022 activist campaign + EPA
  enforcement action (market cap down ~90% since 2022), Parks!
  America's active shareholder dispute, TTEC's withdrawn founder-led
  going-private proposal. Result: every market-cap-covered US company
  now has full qualitative research - **all four coverage dimensions
  for both markets are back in sync with the tier-8 frontier.**

**Shortlist-hygiene items flagged across this round, not acted on**
(per the no-manual-ranked-list-edits policy - surface to the user for
a decision, don't remove unilaterally): TSX:AGTF (delisted 2019),
NasdaqGM:GDEN Golden Entertainment and NasdaqGS:FFIC Flushing
Financial (both completed go-private/merger deals in 2026),
OTCPK:HRGG Heritage NOLA Bancorp (mid wind-down/dissolution). These
four tickers still carry mc_overrides and now thesis data as if they
were live going concerns; worth a deliberate decision on whether to
exclude them from future tiers' target-list generation.

## Dropped delisted/wound-down companies from the US pool (2026-10-08)

User reviewed the four hygiene flags above plus the earlier TSX:ECN
(ECN Capital) flag from the tier-6 round and authorized removing all
five from the pool outright - a deliberate, explicit exception to the
no-manual-ranked-list-edits policy (same class of exception as the
Card Factory GM correction), since these aren't normal screening
misses but companies that no longer exist as going concerns:

- **TSX:AGTF** (AGT Food and Ingredients) - taken private 2019, hasn't
  traded in ~7 years.
- **NasdaqGM:GDEN** (Golden Entertainment) - go-private merger with
  VICI Properties/Blake Sartini, closed April 2026.
- **NasdaqGS:FFIC** (Flushing Financial) - merged into OceanFirst
  Financial, ticker retired, closed June 2026.
- **OTCPK:HRGG** (Heritage NOLA Bancorp) - mid wind-down: selling
  substantially all bank assets, then liquidating the holding company.
- **TSX:ECN** (ECN Capital) - taken private by a Warburg Pincus-led
  group, closed April 2026; had never been added to `mc_overrides`
  (came back `no_coverage` in tier 6, correctly - no public market cap
  to find), so only needed the pool-membership removal, no overrides
  cleanup.

Removed from both pool files (all-sector and non-financial, where
applicable - FFIC/HRGG are banks so financial-sector-only, never in
the non-financial file), `mc_overrides_applied.json`, and the
corporate-actions screened-coverage list. Left their
`corporate_actions.json` entries in place as a factual historical
record - that file logs events, it isn't a pool-membership list, and
other now-delisted/merged companies elsewhere in this project were
handled the same way (kept their corp-action record, just no longer
counted in the live pool).

**US pool size: 517 → 512 companies** (all-sector), 288 → 286
(non-financial). Market-cap coverage: 502 → 498 of 512.

**Lesson for future similar cases**: when a research batch flags a
company as delisted/taken-private/wound-down, that's a different kind
of finding than a normal missing-data gap - it's a question of whether
the company belongs in the pool at all, not what data it needs. Surface
it to the user explicitly rather than either (a) silently continuing to
carry it as if live, or (b) removing it unilaterally - the existing
no-manual-edits policy exists to prevent quietly curating the list, but
a company that factually no longer trades isn't a curation judgment
call, it's a data-accuracy one, once the user confirms it.

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
- USA/Canada market-cap refresh (priority pool) and its corporate-actions
  screen are **done** — only 4 permanently-FMP-blocked market caps
  remain, not worth re-attempting without a plan upgrade.
- US and Europe shareholding research are **done** for their current
  scope (US: 243-ticker priority pool; Europe: 150 thesis companies) —
  see "Shareholding data" and "Coverage extension round" above.
- **Continuing the market-cap / corporate-actions frontier**: market-cap
  coverage now extends to 454-of-1000 (Europe) / 502-of-517 (US/Canada)
  as of tier 7/8 (see above) - the US/Canada pool is now almost fully
  covered, with only 3 tickers left uncovered for documented reasons
  (see that entry). Corporate-actions screening and both markets'
  thesis research are only caught up through tier 6 (two tiers behind
  market-cap now) - the natural next step is extending both to match,
  then (for Europe, which still has real room) the next ~50-company
  market-cap tier, same batch pattern as every round so far (WebSearch
  for non-US-exchange market caps, Canadian TSX/TSXV names, and all
  corporate-actions/thesis
  screening; FMP for US-exchange market caps; never more than one
  WebSearch-heavy agent running at once; generate target lists by
  filtering out already-covered tickers rather than a fixed rank
  window, since re-ranking after each merge can shuffle a window's
  contents; both `data/` and `data-us/corporate_actions_coverage.json`
  now track screened tickers precisely, so future gaps don't need the
  rank-window approximation used for Europe's first catch-up round).
- Europe's qualitative thesis research now covers the full top-354
  (coverage extends as each market-cap tier is caught up - was
  top-150-only) - see above. **US thesis research is now also caught up
  to its full mc-covered set (364/517)** as of the "US/Canada
  qualitative thesis research project" entry above - both dashboards'
  thesis coverage now tracks their respective market-cap frontiers.
  Future market-cap tiers for either market should get the matching
  thesis/corporate-actions extension in the same round (or shortly
  after), rather than letting the gap re-accumulate.
- Once both dashboards are in steady state, the same pipeline can be
  applied to further geography/market-cap datasets the user provides.
- Spin-off / special-situation detection — explicitly deferred to the "last
  part of the project" per the original brief. Not started.
- **Net debt research**: the UI slot exists (both dashboards' full
  financial data drill-down, `c.netDebt`) but no company has a value
  yet - every entry shows "no data yet". User explicitly chose to add
  the UI now and populate later rather than launch research
  immediately. When this is picked up, treat it like gross margin: same
  official-filings-only sourcing discipline, likely same incremental
  per-tier batch pattern, and it'll need its own overrides file
  (`netDebtOverrides` or similar) plus wiring through both build
  scripts' payload - the `c.netDebt` field is currently just a
  pass-through of `c.get('netDebt')` which is always `None` in the
  source data.

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

## Tier-9 market-cap batch, both markets (2026-10-08)

Same batch pattern as tiers 7/8: next ~50 Europe companies by current rank
(filtering out tickers already in `mc_overrides`) via WebSearch, next ~14 US
companies via FMP's `profile-symbol` endpoint (two non-FMP-resolvable
stragglers — TPEX:4971 IntelliEPI, TSX:IFA iFabric Corp. — folded into the
Europe WebSearch batch instead, same as Canadian names in prior tiers).

- **US FMP batch**: 12 targets, 11 ok / 1 not_found (OTCPK:OAKC — the same
  ticker that has failed to resolve in every prior round; still unresolved,
  no further action planned). Two entries were within the 5x/0.2x
  auto-exclude tolerance but flagged by the agent as worth a human glance;
  both were manually WebSearch-verified before merging:
  - **OTCPK:ORBT** (Orbit International Corp., 0.49x vs baseline) — confirmed
    distinct from the unrelated, bankrupt "Orbital Energy Group" (OIG,
    Chapter 11 Aug 2023). FMP's $8.79M is roughly consistent with an Oct 2026
    press-release figure ($8.40M). Looks like a genuine small, thinly-traded
    company, not a data error.
  - **NYSE:CANG** (Cango Inc., 0.58x vs baseline) — WebSearch sources
    conflicted badly (one Benzinga article cited two different market caps
    for the same company; share-outstanding counts disagreed by an order of
    magnitude across sources: 41.02M vs 358.6M vs 341.6M). Accepted FMP's
    self-consistent price x shares figure ($138.81M), which is close to the
    one WebSearch source (Kraken, $138.65M) that roughly agreed with it.
  US/Canada overrides: 498 -> 509.
- **Europe + Canada/Taiwan WebSearch batch**: 52 targets (50 Europe + 2 US
  pool stragglers), all 52 came back "ok" with no ratio outside roughly
  0.6x-1.4x of baseline once genuine price moves were accounted for —
  nothing crossed the >5x/<0.2x auto-exclude threshold. FX rates were
  resolved once per currency (one WebSearch per currency, reused across all
  companies sharing it) and recorded per-entry with source/date. Notable
  findings:
  - **LSE:BPCR** (BioPharma Credit) trades in USD, not GBP — confirmed
    against a separate GBP-denominated line (BPCP) for the same company that
    could easily be confused with it.
  - **BUL:SFA** (Sopharma) had wildly inconsistent share-count sources
    (519.26M vs 166.36M shares, ~35% spread in implied market cap). Used a
    EUR-denominated figure consistent with Bulgaria's Jan 2026 euro adoption
    that best matched the mc0 baseline — flagged as deserving a closer look
    if it resurfaces.
  - **ATSE:EXAE** renamed to "Euronext Athens Holding S.A." (from Hellenic
    Exchanges) in April 2026.
  - **TPEX:4971** (IntelliEPI) confirmed distinct from the similarly-named
    Taiwan ticker 4991 (環宇-KY) that kept surfacing in Chinese-language
    search results.
  Europe overrides: 454 -> 504. US/Canada overrides (from the 2 stragglers):
  509 -> 511.

Both dashboards rebuilt (`build_site.py` / `build_site_us.py`), Playwright-
verified (150 rows, zero JS console errors), committed, and pushed in two
commits (US FMP batch, then Europe+stragglers WebSearch batch).

Coverage after this round: Europe market-cap 504/1000, US/Canada market-cap
511/512 (only OTCPK:OAKC remains uncovered).

## Tier-9 corporate-actions / thesis catch-up (2026-10-08)

Same pattern as the tier-8 catch-up: four sequential WebSearch batches
(never more than one running at once) to resync corporate-actions
screening and thesis research with the tier-9 market-cap frontier.

- **Europe corporate actions** (50 companies, the tier-9 mc-override set
  minus already-screened): 7 findings, 43 clean. Notable: ATSE:EXAE
  (Euronext's completed tender offer for ~74.25% of ATHEX), BVB:PRBU
  (EGM-approved AeRO delisting), ENXTPA:BEN (Beneteau divesting US
  power-boat brands), HLSE:TNOM (Talenom's completed spinoff of Easor
  Plc), LSE:AIRE (active contested hostile takeover - Glenstone vs. AEW
  UK REIT). LSE:AEP and WSE:SEL appear as acquirer, not target. Coverage:
  454 -> 504.
- **US corporate actions** (13 companies): 5 findings, 8 clean. Notable:
  NYSE:CANG's 2025 change-of-control/business-pivot (sold its PRC auto-
  finance business, bitcoin-mining pivot, Enduring Wealth Capital taking
  control), NasdaqGS:RJET confirmed as the post-merger renamed Mesa Air
  Group entity (closed Nov 2025), NasdaqCM:FSEA mid-acquisition
  (Cambridge Financial Group, shareholder-approved but not yet confirmed
  closed). Coverage: 499 -> 512 (now fully caught up).
- **Europe thesis research** (43 companies, top-504-by-rank lacking a
  `thesis` field): all 43 completed. Several companies had genuinely
  limited official-source shareholder data (flagged inline rather than
  papered over): CPSE:FYNBK, BME:TUB, SWX:ZUBN, SWX:BVZN, AIM:VTU,
  AIM:MCON, OM:NMAN, XTRA:GXI (also has an active, unresolved activist-
  investor campaign worth tracking), BIT:ORS. Anti-fabrication re-check
  (full dataset + batch): zero reused shareholder-name/percentage
  combinations.
- **US thesis research** (13 companies, mc-covered lacking `hasThesis`):
  all 13 completed. NYSE:CANG's control change (Enduring Wealth Capital,
  ~49.71% voting power per Cango's own filings) and NasdaqGS:RJET's
  notable red flag (former Republic CEO, now FAA Administrator, reportedly
  missed his ethics-agreement stock-divestiture deadline - a live,
  well-sourced conflict-of-interest story) are worth a second look.
  Anti-fabrication re-check: two regex matches surfaced ("Inc. held
  13.3%"/"7.4%" patterns) but both confirmed as false positives - distinct
  holders, distinct companies, distinct source URLs. US/Canada thesis
  coverage: 511/512 (fully caught up to the market-cap frontier).

All four batches rebuilt both dashboards, Playwright-verified (150 rows,
zero JS console errors), and were committed/pushed as four separate
commits. Both markets' corporate-actions and thesis coverage now fully
match their tier-9 market-cap frontier.

## Tier-10 market-cap batch, both markets (2026-10-08)

Europe's next 50 companies by current score rank, via WebSearch. The
US/Canada pool had only one gap left (OTCPK:OAKC, Oakworth Capital Inc. -
failed to resolve via FMP in every prior round), so it was folded into
this Europe WebSearch batch as company #51 rather than running a separate
US agent.

All 51 came back "ok" - no ratio crossed the >5x/<0.2x auto-exclude
threshold. OAKC finally resolved this round (Motley Fool, $211.69M as of
2026-08-25, corroborated by several other 2026 snapshots in the
$162-212M range, consistent with the $187.1M baseline) - genuine
coverage, not a guess. A few entries had wide cross-source disagreement
and were manually spot-verified before merging:
- **WSE:ASB** (ASBISc Enterprises): some scraped sources implied a ~3x
  jump vs baseline, a currency/unit-labeling error pattern seen a few
  times this round; used the figure that matches baseline almost
  exactly instead.
- **XSAT:ANGL** (Angler Gaming): a Frankfurt EUR line implied ~$260M vs.
  the native Nordic (SEK) listing's ~$27M; used the native listing.
- **WSE:DIG** (Digital Network SA): confirmed genuine ~1.9x rally via a
  consistent implied share count across snapshots - kept as "ok",
  flagged as a large real move worth watching.
- **OM:NMAN, AIM:JDG, HLSE:EQV1V, BVB:ARS**: cross-source spread from
  differing dates/exchanges; used the most recently-dated, best-sourced
  figure in each case.

Both dashboards rebuilt, Playwright-verified (150 rows, zero JS console
errors), committed, and pushed.

Coverage after this round: **Europe market-cap 554/1000. US/Canada
market-cap 512/512 - the US/Canada pool now has zero remaining gaps.**

## Tier-10 corporate-actions / thesis catch-up (2026-10-08)

US/Canada needed almost nothing this round - its corp-actions coverage
was already fully caught up (0 gap), and only one thesis gap remained
(OTCPK:OAKC, whose first market-cap override landed in tier-10). So this
was two sequential Europe-focused WebSearch batches rather than four.

- **Europe corporate actions** (50 companies): 10 findings, 40 clean.
  All ten are bolt-on M&A/divestiture events where the screened company
  is mostly the acquirer, not target (consistent with the established
  "role: acquirer" pattern already in the data): BIT:EQUI (Equita Group
  agreed to acquire Xenon Private Equity, ~doubling AUM to EUR2bn),
  BIT:ORS (Orsero's US expansion via Trucco Holdings/AJ Trucco),
  HLSE:TAALA (Taaleri's completed Nordic Science Investments buy),
  LSE:PRV (Porvair, three bolt-ons), OM:BULTEN (divested its European
  automotive contract-manufacturing arm), OM:NTEK B (Novotek acquired
  70% of ServiTecno), TLSE:TKM1T (TKM Grupp's Skoda-dealership buy),
  WSE:ENT (Enter Air's Nekera acquisition). Two flagged as shakier:
  BME:DESA (only a 2025 LOI verified, closing unconfirmed) and WSE:DIG
  (BGMO acquisition dates to Oct 2025, just outside the 2026 window but
  materially relevant - included with a note). Coverage: 504 -> 554.
- **Europe + OAKC thesis research** (46 Europe companies + OTCPK:OAKC,
  47 total): all completed. Anti-fabrication re-check across the full
  combined dataset: only the same two pre-existing benign false
  positives from the prior round resurfaced (no new duplicates).
  Notable: ENXTPA:ALCIS (Catering International & Services) has an
  official AMF filing showing the founding families held zero shares as
  of May 2023 (pact terminated) yet they still appear in 2024
  leadership - an unresolved discrepancy flagged rather than guessed
  at. OTCPK:OAKC has no 10-K or DEF 14A on EDGAR at all (only 13F-HR/
  Form D filings) - a structural disclosure gap, documented as such
  rather than fabricating a beneficial-ownership table. Several other
  companies (HLSE:SCANFL, SWX:GMI, WSE:ETL, CPSE:RIAS B, BUL:MSH,
  LJSE:SALR, ZGSE:LKPC) had stale, conflicting, or entirely absent
  official shareholder data, flagged inline in each case.

Both dashboards rebuilt, Playwright-verified (150 rows, zero JS console
errors), committed, and pushed as two commits.

Coverage after this round: Europe corporate-actions and thesis research
now both match the tier-10 market-cap frontier (554). **US/Canada
corporate-actions and thesis research are both fully caught up (512/512)
- no gaps remain anywhere in the US/Canada pool.**

## Tier-11 market-cap batch, Europe only (2026-10-10)

US/Canada has nothing left to refresh in this pattern (512/512, no
gaps), so this round was Europe-only: next 50 companies by current
score rank, via WebSearch.

All 50 came back "ok" - ratios ranged 0.53x-1.65x, nothing crossed the
>5x/<0.2x auto-exclude threshold. Spot-verified the two largest declines
before merging:
- **XTRA:ETG** (EnviTec Biogas): 0.53x - a real, large share-price
  decline through 2026 (EUR276-313M in spring/summer down to EUR206M
  by Oct 7), corroborated by two independent sources; no corporate
  action found to explain it.
- **RISE:BAL1R** (AS Amber Latvijas balzams): 0.58x - two independent
  recent sources converge on ~$11-12M, down from ~$58-59M a year
  earlier (an ~80% decline the sources themselves flag as unusual).

Other notable items with real sourcing caveats (kept as "ok", not
flagged): **ENXTPA:CRTO** (illiquid French cooperative bank with wildly
inconsistent aggregator figures depending on share-count convention -
used the full-share-count figure consistent with mc0's methodology),
**AIM:LTHM** (James Latham - sources conflate two share classes, used a
converging whole-company estimate), **LJSE:BKP** and **CPSE:EGNETY**
(lowest-confidence dated sources in the batch, but internally
consistent).

Dashboard rebuilt, Playwright-verified (150 rows, zero JS console
errors), committed, and pushed.

Coverage after this round: Europe market-cap 604/1000. US/Canada
unchanged at 512/512.

**Tier-11 corporate-actions/thesis catch-up (started, then paused by the
user 2026-10-12):** a WebSearch agent screened the 50 tier-11 companies
for corporate actions (25 found:true / 25 found:false - results saved to
`/tmp/.../scratchpad/eu_corpactions_tier11_results.json` in that session's
scratchpad, NOT yet merged into `data/corporate_actions.json`). The user
asked to pause this to work on the two dashboard features below instead.
**This batch's results were deliberately left unmerged** - whoever
resumes this should either merge them (after a sanity read, since they're
already researched and saved) or re-run the screen if the scratchpad file
is gone by then. The tier-11 thesis gap (51 companies) was never started.

## Tracker and spreadsheet export features (2026-10-12)

Two new features added to both dashboards, entirely client-side (no
backend exists or is planned):

**1. Tracker.** Click "Track this company" inside any company's detail
panel - which appears identically in the main table, Biggest movers, Top
150 changes, and Corporate actions modals - to add it to a per-browser
watchlist (`localStorage`, never leaves the device, namespaced separately
per market: `shortlist_tracker_v1` for Europe, `shortlist_us_tracker_v1`
for US/Canada, since both pages share one origin on GitHub Pages and
would otherwise collide). Each tracked company gets an editable
market-cap move threshold (default 10%).

Since this is a static page with no live price feed, "checking" happens
once per page load: the tracked company's officially baked-in market cap
(`c.mc0` - never a local what-if scenario edit, so playing with numbers
in the main table never triggers a false alert) is compared against the
baseline recorded the last time that browser opened the page. A breach:
(a) shows a banner at the top of the page, (b) logs the move in the
Tracker modal with whatever explanation is already on file, in priority
order - a named corporate action (most concrete/dated) > a manually-
researched news note (`c.newsNote`) > the existing rank-mover "cause"
logic (own market-cap/GM change vs. pool ripple, refactored out of
`biggestMovers()` into a shared `causeFromPair()` so both use one
implementation) > an explicit "nothing on file yet" fallback - and (c)
advances the baseline to the new value so the same move isn't re-reported
on every subsequent visit. This is **never a live web search** - the
explanation only ever draws on what's already in the committed dataset.

**2. Download spreadsheet.** A styled, multi-tab `.xlsx` export of the
current top-150 view (respects the live/history-date selector, and on
the US dashboard, respects the sector selector too). Built with
**ExcelJS** (`cdnjs.cloudflare.com/ajax/libs/exceljs/4.4.0/exceljs.min.js`)
rather than the `xlsx.full.min.js` already loaded for the existing
pre-update snapshot export - confirmed via a local Node test that the
open-source SheetJS/`xlsx` build **silently drops cell styling on
write** (a cell's `.s`/fill/font survives in memory but isn't present
when the file is reopened), which would have made a "very neat"
dark-teal-headered export impossible with the library already on the
page. ExcelJS writes real, readable-back styling.

Tabs: Overview, Investment Thesis, Revenue History, Net Income History,
Big Movers, Corporate Actions, Tracker, Methodology - the first four
mirror the layout/column set of the original Europe shortlist workbook
the user attached as a style reference (dark teal `#1B474D` header fill,
white bold Calibri), and the last four are new, per the user's explicit
request to fold in everything the dashboard has grown since that original
workbook (movers, corporate actions, and now the tracker) as additional
tabs rather than leaving the export at its original scope.

**Testing note - a real environment limitation, not a workaround:** this
sandbox's egress proxy blocks `cdnjs.cloudflare.com` entirely (confirmed
via `curl`: 403, "organization policy" on every CDN domain tried,
including `unpkg.com` and `cdn.jsdelivr.net`), so Playwright's browser
can't fetch ExcelJS (or, for that matter, the pre-existing `xlsx.full.min.js`)
in this session. The Tracker (no CDN dependency) was verified end-to-end
via Playwright on both dashboards, including surviving a sector switch on
the US page. The export pipeline was verified differently but just as
rigorously: the *actual* JS shipped in the built `docs/index.html` and
`docs/us.html` was extracted and run under Node with the real `exceljs`
npm package standing in for the CDN script, fed the real production
payload, and the resulting `.xlsx` was inspected with `openpyxl` to
confirm sheet structure, real data values, number formats, and - critically -
that the dark-teal header styling actually persists in the written file.
One bug this caught before it shipped: the US Methodology sheet initially
referenced `BUILD_INFO.mcRefreshedCount`/`gmOverrideCount`, which don't
exist in that dashboard's build-info payload (`scripts/build_site_us.py`
uses `mcOverrideCount` and has no GM-override count at all) - fixed to
use the real field name plus a live-computed GM-verified count. End
users' own browsers will fetch the CDN script with no such restriction;
this was a limitation of testing inside this sandbox only.

Both features implemented identically in `site/template.html` and
`site/template_us.html`.

## Profitability scoring: gross-margin + long-term-growth + CFO-positive bonus (2026-10-12)

A real methodology change, shipped to both pools, after a multi-step
investigation into why ProCook Group plc (LSE:PROC) ranked #162 instead
of top-150 despite strong fundamentals. Two earlier ideas were tried and
explicitly **rejected** before landing on this one - worth preserving the
reasoning since someone will eventually ask "why not just do X":

1. **Trend-based profitability** (redefine a "good" period as NI growing
   vs. the prior period, instead of NI being positive) - rejected: it
   didn't move ProCook at all (its down periods weren't growth-investment
   dips, just real margin compression), and pool-wide it hit 963/1000
   companies with a heavily lopsided effect (907 worse, 56 better),
   punishing ordinary earnings lumpiness across nearly the whole pool.
2. **Standalone revenue-CAGR bonus** (bonus points for >10-15% annualized
   growth alone) - rejected: 72-82% of the pool already clears that bar
   on its own (this is a pre-screened growth/value shortlist), so it
   would've been a near-universal point bump, not a differentiator.

**What shipped instead**: combine three signals that together are much
more selective. A company already in the top gross-margin band (>=60%,
which already earns full GM points) with long-term revenue growth
(full-history CAGR >10%/yr - computed from the first to last *reported*
period; a leading `null` is "no data that period", never treated as zero
revenue, which would otherwise fabricate an absurd growth rate for any
short-history company) that stays broadly cash-generative overall (CFO
positive >=70% of reported periods) gets its `profitability` fixedPts
topped up to the full 16/16, however inconsistent its net income actually
was. Only 54/1000 Europe and 24/512 US companies qualify - the GM gate
does most of the selecting.

**Process**: previewed client-side first (see the "Profitability bonus
preview" entry above - a pure simulation, zero data changes) so the user
could see the exact before/after list before committing to it. Confirmed:
31 of the 54 Europe qualifiers land in the new top-150 (9 genuinely new
entrants, 22 already-shortlisted companies that just climb within it).
Only after reviewing that did the user say to ship it for real.

**Implementation**: `scripts/scoring.py` gained two shared helpers -
`full_history_cagr()` and `apply_profitability_bonus()`. Ran
`scripts/apply_profitability_bonus.py` (one-off correction script) against
`data/companies_1000_scored.json` and both `data-us/companies_pool_*.json`
files, overwriting `fixedPts['profitability']`/`fixedSumNoGm` wherever the
rule qualifies and setting a new `profitabilityBonusApplied: true` flag for
auditability. Also fixed the root US formula
(`scripts/us_scoring.py`'s `compute_fixed_pts`) for consistency if that
pool is ever re-ingested from scratch - Europe has no equivalent ingestion
script in this repo (predates it), so only the stored JSON was corrected
directly, same situation as the dilution and dividend-sign fixes earlier
in this project.

**Result**: ProCook Group: profitability 11.43 -> 16.00/16, total score
85.16 -> 89.73, rank **#162 -> #62** - confirmed live on the real
dashboard (searched for it directly: shows total 89.7). Both dashboards
rebuilt and Playwright-verified (150 rows, zero JS errors). The
"Profitability bonus preview" modal (still present on both pages) now
correctly shows 0 qualifying companies, since everyone who qualified has
already been bonused for real - left in place as a working preview tool
in case the thresholds (60% GM / 10% CAGR / 70% CFO) are ever revisited.

## History slots are yearly, not 4-monthly (2026-10-13)

**Correction of a long-standing misreading.** The 10 `revHist`/`niHist`
slots come from the Capital IQ columns `[LTM-36, LTM-32, ... LTM-4, LTM]`.
The offset is in **quarters**, not months, so consecutive slots are exactly
one **year** apart and the 10 slots span ~9 years (ending with the trailing
twelve months as of the data pull). The raw extract confirms
it: the same file carries `Long-Term Debt [Latest Annual -9 ... Latest
Annual]`, a plain 10-point annual series covering the identical window.
For years the dashboard labeled the slots `Nov 2021, Mar 2022, ... Nov 2024`
(a 3-year, 4-monthly grid). That was wrong - spotted by the user from
ProCook, whose first revenue slot (19.5, USD) is a ~2018-era figure, not
"Nov 2022".

What changed:
- `PERIOD_LABELS` (both templates) -> `LTM '15 ... LTM '24` (trailing 12
  months ending around that year; exact month varies by fiscal calendar).
  **Corrected again 2026-10-13:** the labels first shipped as `'15..'24`, but
  the data was actually pulled after FY2025 results (the screen's "27nov24"
  title is stale), so the slots are `'16..'25`. Evidence: Sopharma Trading's
  LTM revenue/NI/CFO/equity equal its FY2025 results and MONY's LTM revenue
  (600.7 USD) = its FY2025 revenue (GBP 446m x ~1.35); ProCook's LTM-4/LTM
  also line up with TTM to Sep 2024/Sep 2025. Pre-IPO/thin-history companies
  (ProCook) carry older annual figures in their earliest slots. Sopharma's
  Capital IQ numbers were spot-checked against reported figures and are fine.
- **Scoring itself is unaffected** - every dimension (revenue growth,
  consistency, profitability %, CFO %, track record, dilution) reads the 10
  slots as an ordered series, never as dates. So all original scores/ranks
  stand, and the "ranking uses only ~3 years" statement given in chat on
  2026-10-13 was wrong: scores use ~9 years of annual LTM data (fewer for
  companies with short histories).
- **The profitability bonus (2026-10-12) was affected**: its CAGR assumed
  4-month spacing, so every CAGR was ~3x too high and the >10%/yr gate was
  over-awarded. `full_history_cagr()` (scoring.py and the JS in both
  templates) now uses years = last_idx - first_idx. `scripts/
  apply_profitability_bonus.py` was rewritten to be idempotent (baseline is
  always `round(profitPct*16, 4)`, bonus re-derived) and re-run:
  Europe 54 -> 22 companies, US all-sector 24 -> 8, US non-financial 16 -> 6.
  In Europe, 4 companies left the top 150 (Mediclin, Monnari Trade,
  Railcare Group, Wynnstay Properties) and 4 entered (Carlo Gavazzi,
  Vente-Unique.com, Pets at Home, CENIT). ProCook still qualifies
  legitimately (CAGR 31%/yr over 6 years, GM 65.8%, CFO+ in 100% of
  periods) and sits at #58.
- An interim theory in chat that ProCook's early slots were "post-IPO stub
  LTM figures" was also wrong - they are real older annual-scale figures.
  Note all Capital IQ figures here are **USD at the historical rate**
  (column headers say so), not native currency.

## Tier-11 corporate-actions / thesis catch-up resumed (2026-10-15)

Resumed at the user's request after the 2026-10-12 pause.

- **Europe corporate actions** (50 companies, results researched on
  2026-10-12): 25 findings, 22 merged (18 bolt-on M&A, 3 tender offers /
  squeeze-outs, 1 other). Excluded as outside the lookback: AIM:ANP
  (2024-09 bolt-on), MTSE:GO (2024-06 bolt-ons), BIT:KME (2023 tender
  offer; current delisting status unverified). Spot-verified before
  merging: XTRA:A1OS (VINCI EUR67.50 offer - ~83.6% per a secondary source,
  delisting/squeeze-out only intentions), DB:CPX (capsensixx squeeze-out
  effective 31 Jul 2026), TLSE:EEG1T (Ekspress Grupp - bidder ~96%),
  AIM:NICL (VitHit EUR75m), XTRA:CLIQ (partial buyback), ENXTLS:CTT (DHL
  Iberia JV completed 12 May 2026). Coverage 554 -> 604.
- **Europe thesis research** (51 targets): 30 completed and merged; all 30
  passed the field/source/duplicate-text checks. 21 not researched because
  the session hit its shared 200-WebSearch-call budget - list saved as
  `eu_thesis_tier11_remaining.json` in the scratchpad: RISE:BAL1R, NYSE:OEC,
  BIT:EQUI, AIM:MSI, BVB:IMP, CPSE:EGNETY, BIT:PMT, DB:FVI, AIM:NTBR,
  BME:GSJ, WBAG:AGR, WSE:OBL, ENXTBR:COMB, XTRA:SBS, LJSE:BKP, BIT:PHN,
  AIM:NXQ, WSE:PTW, NSEL:VLP1L, WSE:DIG, BVB:VAC. Notable from the merged
  set: Azkoyen has a pending EUR10 cash bid (below the prior EUR11.40
  close); Ekspress Grupp AGM approved a EUR1.26 squeeze-out and delisting;
  Porvair's G.G.G. S.p.A. holds 29.00% (just under the UK 30% bid
  threshold).

**Gross-margin research for fallback companies near the #150 cutoff**
(13 operating companies; banks/insurers/asset managers/property
excluded): results in scratchpad `eu_gm_results_a.json` /
`eu_gm_results_b.json`, NOT merged yet - pending re-verification and a
user decision on Pekabex (FY2025 GM 2.3% in a loss year vs 10.0% FY2024).
Found: WSE:IFI 35.5% (FY2024), NSEL:ZMP1L 23.6% (FY2024), WSE:PBX 2.3%
(FY2025). Not determinable under the source rules (costs by nature, no
gross-profit line): WSE:XBS, ENXTPA:SWP, BUL:AGH, SEP:TOMA, ENXTPA:ALEXA.
Incomplete/not reached (search budget): ATSE:FLEXO, BUL:SFT, ZGSE:MDKA
(group COGS not found), ENXTPA:ALGIL, BUL:ODES.

## Gross margins applied for three near-cutoff fallback companies (2026-10-15)

Written into the base data (`gm`, `gmFiscalYear`, `gmSourceType`,
`gmSourceUrl`, `gmIsFallback=false`) like the original filings-based
research, after re-checking each against the company's own documents:
- **WSE:IFI Ifirma: 35.49% (FY2024)** - 20,679 / 58,273 PLN k, from the
  company's preliminary 2024 ESPI report (confirmed). Same 9.9-pt band as
  the fallback, so no rank effect (#164 -> #163).
- **NSEL:ZMP1L Žemaitijos pienas: 23.62% (FY2024)** - 72,652 / 307,643 EUR k,
  audited 2024 annual report (ESEF). 7.2 pts; #167 -> #274.
- **WSE:PBX Pekabex: 9.96% (FY2024)** - 172,181 / 1,728,162 PLN k, company
  IR results table. **User decision 2026-10-15:** use FY2024 rather than
  FY2025 (2.3%, a loss year with an operating loss of PLN -66.9m), an
  explicit exception to the latest-year rule. Note 9.96% falls just below
  the 10% band boundary -> 1.8 pts; #117 -> #408.
Top-150 effect: Pekabex out, HLSE:TOKMAN (Tokmanni) in.

**Tier-11 thesis follow-up (2026-10-15, later the same day):** the 21
remaining companies were researched (three agents, capped at 7 searches per
company so all four agents fit the 200-call budget), passed the
field/source/duplicate checks against the whole dataset, and were merged -
tier-11 thesis coverage is now complete (51/51). Notable: RISE:BAL1R (Amber
Latvijas balzams) is in court-approved legal protection with >EUR28m tax
debt and a defaulted 90% parent; BIT:EQUI saw Iccrea Banca buy ~15% in
Sep 2026; DB:FVI's controlling holder DEMIRE is in a sale process.

Gross-margin follow-up: ATSE:FLEXO, BUL:SFT, ENXTPA:ALGIL, BUL:ODES remain
on the fallback (no figure obtainable under the source rules - Guillin and
Odessos report costs by nature; Flexopack's FY2024/25 gross-profit line and
Sopharma Trading's consolidated statements could not be read). ZGSE:MDKA:
only a parent-company derived figure found (4.58% FY2025; group COGS not
readable) - awaiting a user decision before applying.

**ZGSE:MDKA Medika - applied 4.58% (FY2025), parent-company figure (2026-10-15).**
User decision: use the parent-only figure (Medika d.d. sales of goods
921,999 minus cost of goods sold 879,783 EUR k, from its own 2025 annual
report filed on the Zagreb exchange) because the consolidated cost-of-goods
line could not be read. The parent is ~96% of group revenue (959,879); the
group includes the Prima Pharme pharmacy chain, so the true consolidated
margin is likely slightly higher - an explicit exception to the
consolidated-figures convention. Below 5% -> 0 GM pts; #126 -> #508.
Top-150 effect: Medika out, DB:MBH3 (Maschinenfabrik Berthold Hermle) in.

## Distress flags (2026-10-15)

Added at the user's request after Amber Latvijas balzams turned out to be in
legal-protection proceedings while scoring benignly on its (historical)
financials. **Informational only - never changes scores or ranks** (same
no-manual-edits rule as everywhere else).

- Data: `data/distress_flags.json` (Europe) and `data-us/distress_flags.json`
  (US/Canada), hand-curated, keyed by ticker: `{level, summary, asOf,
  sources}`; a `_definition` key documents the criteria. `severe` = formal
  insolvency/restructuring/legal-protection proceedings, payment default, or
  a controlling parent in such proceedings. `warning` = going-concern doubt
  in current filings and/or operating under covenant waivers. Historical,
  resolved episodes are not flagged.
- Display: a red "severe distress" / "distress warning" chip on the row's
  meta line (tooltip = summary) and a red box at the top of the shared
  detail panel with the summary, as-of date, source links and a note that
  the score doesn't reflect it. Loaded by `load_distress_flags()` in both
  build scripts, passed through as `c.distress`.
- Initial flags (from a keyword scan of every thesis `red_flags` field, then
  manual review): **RISE:BAL1R** (severe) and **NasdaqGS:CRMT** America's
  Car-Mart (warning). Reviewed and NOT flagged: ProCook (FY23 going-concern
  note, resolved), Roots (2020 US-unit liquidation), Central Pacific (2010),
  Sportsman's Warehouse (2009 Chapter 11 of a predecessor), Cegedim / Mikron
  (a subsidiary in administration/liquidation), Enwell Energy (going-concern
  wording unconfirmed for FY2025 and ~$92-97m cash; its problem is a -92%
  revenue collapse after licence suspensions, not insolvency). Most other
  keyword hits were "no going-concern issues identified" boilerplate.
- Coverage limit: only companies with thesis research (red flags) can be
  screened - Europe ranks beyond the ~604 research frontier aren't covered.
  Re-run the scan whenever new thesis batches are merged.

## Tier-12 market-cap + corporate-actions batch, Europe (2026-10-15)

Next 50 Europe companies by current rank without a refreshed market cap
(ranks 468-645). Two market-cap agents + one corporate-actions agent; all
three hit the session usage limit once and were resumed from their saved
partial results (no work lost).

- **Market caps:** 49 merged (48 ok, 1 flag), 1 not found (ZGSE:AUHR Auto
  Hrvatska - only exchange filings, no price; left on the old value).
  **BIT:OS Officina Stellare flagged at 5.7x** (USD 940M vs old 165M):
  verified genuine - the 1 Jun 2026 reverse-takeover merger with Global
  Aerospace Technologies Group lifted the share count to ~17.4M and the
  company itself states ~EUR800M (Teleborsa, June 2026). Nothing crossed the
  5x/0.2x threshold otherwise. Caveats from the agents: GBP/USD (1.346) is
  from a Jan-2026 source, SEK/PLN from July 2026, RON/NOK/DKK reused from
  tier 11; RTX (May) and PIHLIS (March) prices are stale; share-class
  ambiguity at Gurktaler, Mineralbrunnen and Fotex; Azkoyen and Humana trade
  on live bid terms. **No top-150 effect** (all 50 sit below rank 460);
  biggest rank moves: GAGS 615->483, BTS B 592->717, LGD1L 590->696, NXQ
  601->497, FCMC 633->736.
- **Corporate actions:** all 50 screened, 17 findings, 16 merged (Lectra's
  immaterial, aggregator-only bolt-on excluded). Four are takeovers or
  squeeze-outs of the company itself: BME:AZK (Ohmnia EUR10 bid, pending),
  XTRA:D6H DATAGROUP (KKR EUR54, settled Nov 2025 per the agent; I could
  only re-verify the April 2025 announcement, flagged in the note),
  OM:HUM Humana (Ambea offer 90.84% accepted, declared unconditional 1 Oct
  2026, acceptance extended to 14 Oct - verified against Placera/offer
  documents), ENXTPA:FCMC (SPD buyout + squeeze-out, AMF review pending).
  ATSE:QUEST is the *seller* of its ACS courier unit (GLS call option
  exercisable 30 Oct 2026). Coverage 604 -> 654.
- **Pending:** tier-12 thesis research (34 companies still without one) -
  split across turns because the shared 200-WebSearch budget per turn can't
  fit all of them.

## Tier-12 thesis research, Europe (2026-10-15/16)

34 companies researched in five agent batches (three had to be restarted
after a usage-limit stop with nothing saved; the rest completed cleanly at
4-6 searches per company). All 34 passed the field / source-URL /
cross-dataset duplicate-text checks, merged, rebuilt and pushed. Neither the
tier-11 nor tier-12 merge overwrote any existing thesis text (verified
against the pre-merge commits).

- **No new distress flags.** Scanned all 34 red-flag texts. ENXTLS:ESON
  (Estoril Sol) is the closest: 2025 loss EUR17.9-25.3m, a reported need to
  reinforce equity by ~EUR35m for Gaming Law requirements, lost Povoa
  concession, and an unread EUR36.9m tax-penalty headline - but no
  going-concern doubt or insolvency proceeding, so it does not meet the
  documented criteria; surfaced to the user instead. OM:MANG filed a
  bankruptcy petition against a *counterparty*, not itself.
- Notable ownership/control: BIT:OS post-merger holders (GATI/Investindustrial
  59.38%, free float ~15%); ENXTAM:AJAX association 73%; ENXTPA:FCMC SPD
  92.18% with a pending EUR2,700 buyout + squeeze-out; DATAGROUP's Munich
  m:access delisting confirmed (revocation effective 30 Jun 2026), Xetra
  status unconfirmed; OM:HUM delisting application filed ~6 Oct 2026.
- Many holder tables are aggregator-only, stale (some 2014-2023) or conflict
  between sources; each entry flags this in its own text.

**Data-hygiene finding:** the pool file's `hasThesis` flag had drifted from
reality (177 companies had full thesis text with `hasThesis=false`; nothing in
the scripts or templates reads the flag). It is now synced to
`bool(thesis)`. Earlier coverage numbers in this brief that were derived from
the flag understate real coverage. **Actual thesis coverage after tier 12:**
ranks 1-300 complete (300/300), ranks 301-700 339/400, ranks 701-1000 3/300
(642 of 1,000 overall). Use `bool(thesis)`, not `hasThesis`, in any future
gap computation.


## Tier 13 (Europe) - market caps + corporate-actions screen (2026-10-16)

- **Market caps:** 50 companies (current ranks 622-697, the next 50 without an
  override) refreshed by two agents at <=2 searches/company: 50 ok, 0 flag,
  0 not_found; all ratios vs. the Capital IQ cap within 0.74-1.68. Added to
  `data/mc_overrides_applied.json` (now 703 entries; file kept in its original
  single-line format). Weak spots recorded by the agents: FX rates are
  aggregator quotes from 16 Sep-12 Oct; undated or stale (>4 months)
  snapshots for TSX:GEO, AIM:ALU (Feb 2026), OM:NEOBO, HLSE:ACG1V,
  ENXTAM:FFARM, MUN:KUL, HLSE:SIILI; undated ENXTPA:MRN (+68%, read as a
  genuine rise), BIT:CIRC (lower confidence), WSE:GOB, ZGSE:CTKS (price x
  202,345 shares), ATSE:GEBKA (implied share count). Refresh these first if
  precision matters.
- **Corporate actions:** all 50 screened (60 searches); 16 findings appended
  to `data/corporate_actions.json` (append-only, indent=1): 1 tender offer
  (ZGSE:CTKS is the *target* of SQ Capital's EUR43 bid; only 0.61% tendered,
  no delisting), 8 acquirer bolt-ons, 2 spin-offs (OM:UPSALE/Aira completed;
  WSE:SNT/Syn2bio approved, debut unconfirmed), 5 "other" (WSE:NVT strategic
  review that may bring in an investor; ENXTAM:TRIO German wind-down;
  ICSE:SYN, BME:ALNT, ATSE:FOYRK divestitures). Coverage now 703 screened.
  No company is being taken over/delisted other than the CTKS bid.
- **Not done:** tier-13 theses (49 of the 50 have none) - next round, since
  the 200-search/turn cap is shared across agents.
- **UI fix:** expanded company details inside the "Biggest movers" modal (and
  the other modals) no longer scroll horizontally - grid columns can shrink
  and long strings wrap (`site/template*.html`).

## Tier 14 (Europe) - market caps + corporate-actions screen (2026-10-16)

- **Market caps:** next 50 companies without an override (ranks 684-745).
  48 ok, 2 not_found, 0 flag; all ratios 0.3-3x vs. Capital IQ (highest
  IPE 1.89, a genuine tripling per the agent). Added to
  `data/mc_overrides_applied.json` (now 751). **No override** for
  ENXTBR:WHATS (What's Cooking - taken private and delisted ~28 Jul 2026;
  verified: families reached 100% via squeeze-out) and LSE:FORT (Forterra -
  aggregator figures inconsistent; listing status unconfirmed) - both keep
  their Capital IQ cap. Weak spots: undated or >2-month-old prices for TTR1,
  KGL, SWG, VBL1L, BOOT, ASCO, NRST, FAR, FOBANK, RTC, SWTQ, NEOH, HBLN, STEF,
  ERNT (30 Mar), LWB (30 Apr), ELTON, YAN, SAF1R; share-count conflicts for
  INWI, AAG, PACT, ASCO, PZV1L, ADE, CCN (whole-company price x shares used);
  ISK rate is from 10 Jul; part-2 FX is 31 Aug.
- **Corporate actions:** all 50 screened (58 searches); 18 findings appended.
  **Six companies are bid targets**: BME:ECR Ercros (Bondalti exclusion bid
  EUR3.505 accepted by 8.62% of capital -> Bondalti 85.85%, settlement 21 Sep,
  trading ended ~22-23 Sep 2026 - verified on a second search, so the ranked
  row is a delisted stock; its override is the bid-driven last price);
  ENXTBR:WHATS (EUR148 take-private, delisted ~28 Jul 2026, verified);
  ENXTPA:GPE Pizzorno (Paprec mandatory offer EUR62.50, pending; price
  pinned to the offer); LSE:IDHC IDH (Hena mandatory offer USD0.50, Hena
  ~56.7%, still listed); ENXTLS:MAR Martifer (Visabeira offer closed, 0.24%
  tendered, no squeeze-out); WSE:FHB FoodHub (Sept 2025 tender call PLN2.70,
  structure unclear). Others: asset sales by SWTQ/BOOT; acquirer bolt-ons
  (STEF B, PACT, INWI, HBLN); NEOH 20.3% stake purchase; PZC 31.4% block;
  SKAGI/Islandsbanki merger talks ended Feb 2026; POMRY/Henkell talks ended
  Aug 2026; AAG 10% self-tender completed; KGL strategic review. Coverage now
  753 screened.
- **Open decision for the user:** delisted/delisting names (ECR, WHATS) remain
  in the ranked list - per the standing "no manual removals" policy they are
  only annotated via the corporate-actions section. Say if you want a rule for
  excluding companies with completed delistings.
- Theses for tier-13/14 targets still outstanding (~98 companies).

## Tier 13/14 theses (2026-10-16 to 10-19)

- 97 companies (tier 13+14 targets without a thesis; the delisted ECR and
  WHATS skipped) researched in three rounds (35 / 35 / 27) at <=5 searches per
  company; two rounds were interrupted by a session-limit stop and resumed
  (nothing lost). All 97 passed the field / source-or-gap-marker /
  duplicate-sentence checks and are merged. **Thesis coverage is now 739 of
  1,000** (ranks 1-300: 300/300; 301-700: 391/400; 701-1000: 48/300). Still
  without a thesis in ranks <=700 (they were never in a market-cap tier
  batch): AIM:JHD, DB:CPX, WSE:APT, BVB:IARV, OM:PROF B, LSE:MER, BVB:SNO,
  CPSE:SKJE, XTRA:SFQ.
- Quality caveats written into the entries themselves: many holder tables are
  aggregator-only (Simply Wall St etc.) or stale (2013-2024); websites not
  seen in search results are marked "Not confirmed in search results".
- Corrections found by the thesis agents and applied to
  `data/corporate_actions.json`: ENXTPA:EDI (Media 6) squeeze-out added (23 Jun
  2026, confirmed on a second search); WSE:FHB tender call outcome clarified
  (company bought 914,936 shares; no delisting); **OM:PACT**: the screen's
  "Sepago, Jul 2026" item was a mis-dated article (Sepago was bought in 2022) -
  replaced by the verified Consular ApS bolt-on (Oct 2025).
- Notable flags in the new theses: IDH (Hena ~56.7% after unrecommended
  mandatory offer), Cateks (SQ Capital concert ~65%, thin float), Ropczyce
  (shareholder-agreement bloc fell 83.1% -> 63.0%), ADE (value rests on a
  crypto treasury; one source reports a MiCA authorisation rejection),
  Pommery (court-approved conciliation protocol, heavy debt), Forterra (still
  listed per a 12 Oct 2026 buyback notice; no official register check).
- Distress keyword scan over the 97 new red-flag texts done: one new flag,
  ENXTPA:POMRY (Pommery) at level "warning" (court-approved conciliation
  protocol, heavy debt, financing only to Jun 2027; no payment default or
  insolvency proceeding, so not "severe" - the user can upgrade it).

## Tier 15 (Europe) - market caps + corporate-actions screen (2026-10-19)

- **Market caps:** next 50 without an override (ranks 707-798): 49 added
  (`data/mc_overrides_applied.json` now 800), all ratios 0.6-1.98 vs. Capital
  IQ (largest: Kinepolis 1.98, Gremi 0.60). ENXTBR:WHATS skipped (delisted
  July 2026, already recorded). LSE:FORT now has a figure (earlier tier-14
  attempt had none). Weak spots: several caps computed (price x shares) rather
  than quoted (BLO, ODL, LBW, BSL, ILYDA, KTJV, PAT, 11B, ICGC); undated
  (IBG, ISUR, JST, RING, HES, MASI, MPC, PCTN, NEDAP, VDM, Goldplat, Merko);
  4+ months old (CAI, ECK, IATR, Fintel-sourced one); BSL EUR22.20 vs 27.3
  conflict; low confidence AmRest, Goldplat, MPC. FX: BdF 16 Oct (part 1),
  mql5/Bundesbank 8-14 Oct (part 2).
- **Corporate actions:** 50 screened (62 searches); 17 findings appended
  (WHATS duplicate skipped). Company-is-target situations: LSE:PCTN Picton
  (LondonMetric/SREIT scheme effective 10 Sep 2026, trading cancelled ~11 Sep
  - **delisted**, verified); WBAG:ADKO Addiko (contested RBI vs NLB offers;
  press accounts conflict, outcome unconfirmed); ENXTPA:ALVDM Voyageurs du
  Monde (Avantage OPR + squeeze-out at EUR180, held 86.59% already; indicative
  window 28 Oct-10 Nov, AMF clearance not confirmed - verified); LSE:ICGC
  Irish Continental (EUR8.00 management buyout, expected Q4 2026); WSE:KVT
  (PLN9.37 delisting tender Jul 2025, KNF suspended the delisting in May
  2026); stake deals WSE:GME (56.82% via share swap), MTSE:MPC (BMIT 49%).
  Acquirer/other items: JST/Hyva, GYLD B, SIRM, EVER, CHRT, FF, KIN; CRI and
  AURE divestitures; PARKEN strategic review. Coverage 801 screened.
- Rows now delisted or about to be (PCTN, WHATS, ECR, EDI): still in the
  ranked list, annotated only via corporate actions - open decision for the
  user on an exclusion rule.
- 200 companies in the Europe pool still have no override (ranks ~800+; includes WHATS, delisted).

## Tier 16 (Europe) - market caps + corporate-actions screen (2026-10-20)

- **Market caps:** next 50 without an override (ranks 789-847): 49 added
  (`data/mc_overrides_applied.json` now 849; ratios 0.65-2.13). **No override
  for LSE:TET** (Treatt - taken private by Dohler at 305p, delisted 3 Jul
  2026; keeps its Capital IQ cap). Large moves look genuine (James Cropper
  2.13 after a strong trading update; Kaufman & Broad 0.65). Weak spots:
  undated (Dinkelacker, Avicola Slobozia, CTT, Harvest Tech, Moara Cibin,
  Econocom, HiTechPros, Atelierele CFR, Bonasudden, HAE1T, BIOKA, LKRI -
  currency assumed EUR, low confidence -, FHW, ELIN); 4+ months old (ALCM,
  WIIT, BERG B, STRN, Elma, Moda Bagno, Antibiotice); Dinkelacker share-count
  conflict; FX = ECB/other reference rates from mid-Sep 2026 (no October
  rates found).
- **Corporate actions:** 50 screened (59 searches); 18 findings appended.
  Bid targets: LSE:TET Treatt (Dohler 305p scheme, delisted 3 Jul 2026);
  OB:ELMRA Elmera (Fortum NOK47 offer, ~91.6% accepted, settlement ~23 Oct,
  delisting intended but unconfirmed - verified); OM:BAHN B Bahnhof (Telenor
  buying 57.5% at SEK60-62 then mandatory offer at SEK62, approvals pending -
  verified); DB:FHW Fernheizwerk Neukolln (BEW delisting offer announced 24 Sep
  2026; the EUR24.20 price quoted by the screen could NOT be confirmed);
  ENXTAM:CTAC Ctac (Value8 mandatory offer EUR3.50 from Apr 2025; outcome not
  found). The rest are acquirer bolt-ons (FM, PRT, IEG, IBAB, PERF, BOW,
  BONAS, BERG B, TRIONA, HMU, MONB, GRN, SPEL). Coverage: 851 screened.
- Delisted / being delisted rows still in the ranked list: PCTN, WHATS, ECR,
  EDI, TET (and ELMRA, ALVDM, BAHN B pending). Exclusion-rule question remains
  open with the user.
- 149 companies in the Europe pool still have no override (ranks ~850+).

## Tier 17 (Europe) - market caps + corporate-actions screen (2026-10-20)

- **Market caps:** next 50 without an override (ranks 838-900): 49 added
  (`data/mc_overrides_applied.json` now 898; ratios 0.56-1.63). **No override
  for HMSE:S9I** (Stemmer Imaging - taken private by MiddleGround, delisted
  ~27 Dec 2024). Caveats: FX is Aug-Oct reference rates (up to ~2-3% error;
  GBP/CHF 1 Jul); undated (ZPKL, SEC, COOR, ELSTR, ACI, PFB, AKKO, PEH, ULM,
  AQU, FIH, ALSTW); KINGS ~8 months old; ZPKL cap could be ~1.8x higher if an
  Oct 2025 capital increase is not in the share count; HARB B share-class
  conflict (range USD 69-107m, 88m used); HAS share count (Sep 2025) unverified
  (1.63x); ALHEX possibly overstated; APTD share count derived.
- **Corporate actions:** 50 screened (57 searches); 15 findings appended.
  Bid targets: AIM:GHH Gooch & Housego (Arlington 1,230p cash, court-sanctioned,
  delisting imminent - verified); WSE:ECH Echo Investment (Lisala, 62.37%
  holder, tender at PLN5.20 for 37.63%, a ~4% DISCOUNT to the market price,
  possible delisting - only secondary sources); ZGSE:ZPKL Klara (Cakovecki
  mlinovi EUR120.25 bid approved Feb 2025, bidder ~89.5%; delisting proposal
  unconfirmed); LSE:APTD Aptitude (formal sale process since Apr 2026);
  LSE:PPH PPHE (Fattal proposal collapsed Jul 2026); HMSE:S9I Stemmer
  (delisted Dec 2024, recorded though pre-window). Others: CSE:PHL, ALHEX,
  PEH (subsidiary squeeze-out), CCR, ORIOLA, FIH, ABJC, HAS, EYDAP.
  Coverage: 901 screened.
- 99 companies in the Europe pool still have no override (ranks ~900+).

## Tier 18 (Europe) - market caps + corporate-actions screen (2026-10-20)

- **Market caps:** next 50 without an override (ranks 897-951): all 50 added
  (`data/mc_overrides_applied.json` now 948; ratios 0.75-2.80; GR6 Gradus 2.80
  is a genuine rally). Caveats: FX = Banque de France 15-16 Oct 2026 crosses;
  PDBA price dated 5 Dec 2025 (AikGroup deal implies ~EUR46m); CTG, PVT, GFM,
  ADPL ~4 months old; undated AVT B (low confidence, SEK171-282m), SKMO, KBG,
  JDW, Foamit, BayWa (low confidence), Toplofikatsia-Ruse, Viktor Lenac,
  Kompap; Grupa Azoty may exclude a planned 33.7m-share issue (+34% if
  registered); RS2 ordinary shares only; computed (price x shares) values for
  ERB, GR6, TOR, GBT, ATRAV, NAE; share-count disagreements for Passus, Lenac,
  Allerthal.
- **Corporate actions:** 50 screened (61 searches); 21 findings appended.
  Company-is-target (second-search verified where noted): XTRA:PSAN PSI
  Software (Warburg Pincus EUR45 offer, >82% control Jan 2026, delisting
  intended; the screen's "delisting offer Sep 2026" NOT confirmed); DB:CTNK
  centrotherm (Ardian control closed 18 Dec 2025, squeeze-out requested 17
  Dec 2025); ENXTPA:NAE North Atlantic Energies/Esso SAF (82.89% bought at
  EUR26.19, simplified offer EUR28.93, squeeze-out intended); BUSE:RABA (4iG
  74.34%, HUF1,789 offer no acceptances, second bid HUF3,425 closed 27 Apr
  2026, competition approval pending); ZGSE:PDBA (AikGroup 91.75% at EUR68.8,
  mandatory offer to follow); SWX:APGN (NZZ to 45%); WSE:SLV strategic review;
  WSE:TOR State stake sale pending. Others: acquirers GR6, MCAP, REVOIL,
  FOAMIT, BRK; ATT/BYW/GBT restructuring-type items; PANNERGY/PAS buybacks;
  POSTI state IPO sale. Three pre-2025 events were dropped by the agent.
  Coverage: 951 screened.
- 49 companies in the Europe pool still have no override (ranks ~950+; includes
  WHATS, TET and S9I, which are delisted and deliberately left alone).

## Tier 19 (Europe) - final market-cap + corporate-actions batch (2026-10-20)

- **Europe pool is now fully covered**: market-cap overrides on 997 of 1,000
  companies (only the three delisted names WHATS, TET and S9I keep their
  Capital IQ cap) and all 1,000 screened for corporate actions.
- **Market caps (ranks 947-1000):** 49 added, ratios 0.68-1.54. Weak spots:
  most prices 2-4 months old (only LGT 1 Oct, INTA 5 Oct, CONTX 8 Oct, VLE 21
  Sep, TIV 11 Sep recent); LIB ~Feb 2026, DOMIK Mar 2026, Camellia/Sif/
  Wielton/Conect >4 months; undated LAY (nominal price, no trades), LRH, LUS1
  (sources EUR138-188m), PZS, Nordecon, Mostostal Warszawa, Tamex, Prefab, SIT,
  Foraj Sonde (volatile); ED4 uses ~37.5m shares (25m + 12.5m new, confirmed by
  the Jun 2026 ad hoc); share-count conflicts: WJG, CONTX (inferred), VLE
  (treasury shares), KSL (A/B), Saga Furs (3.54m vs ~2.7m), Suominen (135.4m
  after Jul 2026 rights issue), FACC (EUR735-797m), Nexity (EUR394m used vs
  PitchBook USD504m).
- **Corporate actions:** 49 screened (65 searches); 17 findings appended.
  Target: ENXTPA:SACI Fiducial Office Solutions (Fiducial SC 99.8% holder,
  squeeze-out offer EUR36, info note 8 Oct 2026, delisting indicatively week of
  26 Oct - verified). Stake / control events: BME:TLGO (Sidenor-led 29.76%),
  BVB:PREH (Celco 65%), BVB:INTA, ZGSE:LRH (holder reviewing sale), ENXTLS:SLBEN
  (minority sale reportedly collapsed), XTRA:ED4 EDAG (ATON to 83.1% via EUR75m
  raise - verified, no delisting). Other: CSE:LUI trading suspended Aug 2025,
  WSE:FEE strategic review, SUY1V rights issue, WLT subscription, JSW and CAM
  disposals; acquirers SVIK, SIT, LUS1, KSL. Coverage: 1,000 screened.
- **Open items** (unchanged): exclusion rule for delisted rows (PCTN, WHATS,
  ECR, EDI, TET, S9I; pending ELMRA, ALVDM, SACI, GHH, BAHN B, PSAN...);
  theses for the 261 Europe companies without one (tiers 15-19 plus older
  gaps); US refresh / GM gaps; Sopharma Trading and Flexopack GM; Spectra
  Systems US thesis description.

## Europe theses completed (2026-10-19 to 10-21)

- **Thesis coverage: 995 of 1,000.** The five without one are deliberately
  skipped delisted names: ENXTBR:WHATS, BME:ECR, LSE:PCTN, LSE:TET, HMSE:S9I.
  (ENXTPA:EDI/Media 6 has one, written before its squeeze-out was found.)
- Ran in rounds of 35 (5 agents x 7, <=5 searches/company), ~256 companies in
  all, merged via a scratchpad script that checks field presence, a source URL
  or an explicit research-gap marker per field, and cross-dataset duplicate
  sentences. Repeated "could not locate ..." boilerplate is expected and fine.
  **Process incidents:** two usage-limit stops mid-run (resumed; placeholder
  entries for LUS1/GR6/ALLHB were NOT merged and were redone); the scratchpad
  was wiped once (repo unaffected; scripts rebuilt).
- **Thin entries worth a rerun** (agents hit the search limit after only 2-3
  searches each): round 6 parts 2-4 - HLSE:FOAMIT, ZGSE:VLEN, OM:ELAN B,
  BUSE:PANNERGY, OM:AVEN, WBAG:RAT, ATSE:REVOIL, ZGSE:PDBA, BUL:KBG,
  XTRA:BYW, WSE:PAS, BUL:TPLR, LSE:FSTA, LSE:BRK, WSE:PPS, WSE:ELT, LSE:HAS,
  ATSE:ATTICA, WSE:ZUE, WSE:KMP, WSE:SFD (competitive position / insider
  holdings / websites mostly marked as gaps).
- **Distress flags now:** RISE:BAL1R (severe), ENXTPA:POMRY (warning),
  WSE:MSW Mostostal Warszawa (warning: negative equity + disclosed going-concern
  threat + PLN375-520m recapitalisation need; Acciona 62.13%). Considered and
  NOT flagged (no confirmed going-concern/waiver/proceeding): ENXTPA:GBT Guerbet
  (agent claimed covenant waivers; second search found only the FDA warning
  letter and a guided debt/revenue hit), XTRA:KTA Knaus Tabbert, XTRA:ED4 EDAG,
  CSE:LUI Louis, ENXTPA:NXI Nexity, ENXTLS:ESON Estoril Sol.
- Corrections applied to `data/corporate_actions.json` from thesis research:
  ENXTPA:EDI (squeeze-out added), WSE:FHB, OM:PACT (Sepago was 2022, replaced by
  Consular), XTRA:PSAN (delisting agreement 8 Sep 2026 at the statutory minimum
  price), ENXTPA:NAE (squeeze-out reportedly dropped), BVB:PREH. Unverified
  entries still present: BVB:EVER (North Lake stake), WSE:ECH (single
  secondary source), WBAG:ADKO (conflicting accounts).
- **Open decisions for the user:** exclusion rule for delisted/delisting rows;
  whether to rerun thin entries; US refresh (market caps weeks old, 208 GM
  unverified); Sopharma Trading / Flexopack GM; Spectra Systems thesis text.

## Delisted-company rule (2026-10-21)

- **Rule (agreed with the user):** a ranked company whose delisting / takeover /
  squeeze-out has **completed** (verified from at least one source) is hidden
  from the Europe dashboard's main table and "Biggest movers", and listed in a
  new **Delisted** window (button next to Corporate actions) with date, deal
  price, reason and sources. Announced or pending offers are NOT hidden - they
  stay visible and are annotated in Corporate actions.
- **Implementation:** `data/delisted.json` (hand-maintained, `_definition` inside),
  loaded by `scripts/build_site.py` into `payload.delisted`; `site/template.html`
  filters in `render()` and `biggestMovers()` and renders the window. The
  companies **stay in the scoring pool**, so no other company's score or rank
  changes and displayed ranks keep their gaps (hidden rows' ranks are shown in
  the Delisted window as "would rank #N"). The US dashboard has no delisted
  list (none known) and its template is unchanged.
- **Currently listed (7):** ENXTBR:WHATS, BME:ECR, LSE:PCTN, LSE:TET,
  HMSE:S9I, ENXTPA:EDI (Euronext's own notice not located), DB:CPX.
- **To add a name when its delisting completes:** add an entry to
  `data/delisted.json` and rebuild. Candidates to watch: OB:ELMRA, AIM:GHH,
  ENXTPA:SACI, ENXTPA:ALVDM, XTRA:PSAN, DB:CTNK, LSE:ICGC, OM:BAHN B, DB:FHW.

## US/Canada gross-margin research (2026-10-21)

- **Scope:** of 208 US/Canada companies without a verified GM, 154 are
  financial-sector (banks, insurers, asset managers; GM not meaningful, left
  alone by design) and **54 are non-financial**. 4 agents (WebSearch only,
  <=3 searches/company, company filings / IR releases only) researched the 54.
  Full per-company outcome (incl. reasons) is in `data-us/gm_research_log.json`.
- **Applied (11)** into both US pools (`gm`, `gmIsVerified`, `gmFiscalYear`,
  `gmSourceUrl`; `build_site_us.py` now shows the FY and a "Company filing"
  link): NYSE:HY 16.8%, NasdaqGS:PKOH 17.0%, NasdaqGS:CCRN 20.3%,
  NasdaqGS:TBRG 53.0% (cost excludes D&A, so flattered), NYSEAM:INFU 56.0%,
  NasdaqGS:TTEC 21.8%, NYSE:TRAK 85.8% (computed from "cost of revenue and
  product support"), OTCPK:FTCO 54.1% ("mine gross profit"), NYSE:AVD 28.6%,
  NasdaqCM:DLHC 18.9% (computed from "contract costs"), NasdaqGS:DLTH 53.4%.
  `scripts/apply_profitability_bonus.py` re-run: no change to the bonus set.
- **Effect (US all-sector view):** having a GM turns on valuation lens A, so
  several jumped: DLTH #489->#137, TTEC #407->#136, TRAK #345->#147, INFU
  #419->#205, AVD #422->#236, TBRG #488->#267 (market caps are weeks old - the
  US refresh is still pending, so treat these as provisional).
- **Not applied:** NasdaqCM:JYNT (79.6% - cost line unverified on a second
  search), NasdaqGS:CRMT (vehicle-only 35.4%, finviz reprint), partials DNUT,
  ARKO, LEGH, PRKA, ISC; not found DRM, LICT, IEHC (FY2025 ~26% implied, no
  company document), MNPP; **no gross-profit line (~30)**: CFP, MMI, MRTN, UTL,
  MRC, AGF.B, CF, SNCY, RJET, HTLD, BJRI (food-and-beverage cost only), CABO,
  FWRD, MCS, YORW, ARTN.A, IFP, CKI, OAKC, PAMT, CXI, CPTP, MAYS, LPA, UFC, IEI,
  CKX, AMEN, MXC, CPHC, NUVR, ARKR. Several of those classifications rest on
  search extracts of the statement structure (noted in the log).

## Per-company comments (2026-10-21)

- Both dashboards (Europe and US/Canada) now have a **Comments** feature:
  a comment box at the bottom of every company's detail panel (right after the
  collapsible "Full financial data"), each comment stamped with the local date
  and time, newest first; add with the button or Ctrl/Cmd+Enter; delete with
  confirmation. A 💬 n tag appears in the company's table row. A **Comments (n)**
  button opens a window with all comments across companies, newest first,
  with "show in table", Export (JSON backup) and Import (merge by comment id).
- **Storage (two layers):** (1) **saved comments** live in the repo in
  `data/comments.json`, next to the market caps, are embedded read-only in both
  pages at build time (`payload.savedComments`, shown as "saved to repo") and
  therefore show on every device; (2) **new comments** are written to browser
  `localStorage` (`shortlist_comments_v1`, shared by both pages) and flagged
  "browser only - not backed up yet" until saved. **Saving workflow:** the user
  clicks Export in the Comments window (a JSON file with ALL comments) and
  gives the file to Claude, who runs `python3 scripts/merge_comments.py
  <file>` (de-dupes by comment id), rebuilds both pages, commits and pushes.
  Saved comments cannot be deleted from the page - ask Claude to remove one
  from `data/comments.json`. No backend exists (Cloudflare Workers static
  assets behind Access); an automatic synced store would need a Worker + KV
  namespace (the user must authorize the Cloudflare connector or give a KV
  id) - offered, not built.
- Implementation lives in `site/template.html` and `site/template_us.html`
  (`initComments()` etc.). Also fixed a stale hard-coded "790/1000 covered" GM
  coverage figure in the Europe header (now computed).

## Cloudflare-backed comments (2026-10-21) - activated

- `worker/index.js` (+ `worker/README.md`, `worker/wrangler.activated.jsonc`,
  `worker/test_local.mjs`): a Worker adding `/api/comments` (GET/POST/DELETE,
  per-user via the Cloudflare Access email, stored in KV key
  `comments:<email>` with dated `backup:` copies). Tested locally with the real
  Worker code + in-memory KV + browser: add, second-device read, delete, 401
  without Access, graceful browser-only fallback.
- Both page templates now have three comment layers (repo `data/comments.json`
  -> Cloudflare KV -> browser localStorage), merged by id; the page syncs
  automatically when it is served by the Worker and silently falls back
  otherwise (file://, API missing, not logged in).
- **To activate:** create a KV namespace, copy `worker/wrangler.activated.jsonc`
  over `wrangler.jsonc` with the id, push to the branch Cloudflare deploys
  (see README). Pending the user's Cloudflare connector authorization (or a KV
  id) and confirmation of the deploy branch. `wrangler.jsonc` was deliberately
  left unchanged so a missing binding cannot break the live deploy.

- **Activated:** the user created KV namespace `financial-dashboard-state`
  (id `e65191f8f3af4477ad405715098f267a`); `wrangler.jsonc` now carries `main`,
  the `ASSETS` binding with `run_worker_first: ["/api/*"]`, the `STATE` binding
  and `preview_urls: false`; `wrangler@4 deploy --dry-run` passes. The only git
  branch on the remote is `claude/gracious-goldberg-v4yuql`, assumed to be the
  one Cloudflare deploys. To verify live: open `/api/ping` on the site (should
  return `{"ok":true,"email":...}`), add a comment, then open the site in a
  second browser. If it fails check the Workers Builds log and that the Access
  application covers all traffic on the hostname (incl. `/api/*`).

## IPO-era share-count artefact in the dilution gate (2026-10-26)

**Problem.** The dilution gate (last / first reported diluted share count − 1 ≤ 20%)
reads Capital IQ's "Weighted Avg. Diluted Shares Out." slots. For a company that
listed inside the 10-slot window, the first slot is a pre-listing / part-year
stub (Trainline 1.1m → 427m, Funko 0.2m → 50.6m, Angling Direct 4.65m → 45.4m),
so dilution read as hundreds of percent although nothing was diluted.

**Rule** (`scripts/dilution_rule.py`, `measure_dilution`): if either of the first
two year-on-year steps of the share-count series is a jump of ≥ 2.0×, the counts
before the jump are ignored and dilution is measured from the first post-jump
count to the last — only when ≥ 3 counts remain after the jump. A company that
keeps issuing after listing still fails: **Angling Direct (AIM:ANG) is still
excluded** (45.4m → 77.5m = +71% after its IPO ramp is genuine placings).
`scripts/ingest_us_pool.py` uses the same function, so a fresh ingest agrees.

**Applied by** `scripts/ipo_artefact_fix.py` (idempotent), both pools:
- Europe: 37 companies that passed every other gate were added (pool 1,000 → 1,037;
  best new rank #205 on GM-fallback scoring; none in the top 150 yet) and Selvita
  (WSE:SLV) was re-scored (dilution 11.7% → −1.1%). USA/Canada: 8 added (pool 512 → 520).
- New entries carry `dilutionAdjusted: true`, `gm: null` (pool-median fallback) and
  no thesis until researched; their market caps are the raw-extract values until
  refreshed. The template's pool-size text is now computed from the data.
- Caveat: the original pool was "top 1,000 of the 1,816 gate survivors by a
  preliminary pre-GM score"; that preliminary score cannot be reproduced, so the
  rescued names are appended rather than competing for the 1,000th place.
- Known pre-existing quirk: `is_financial_sector` in `ingest_us_pool.py` lower-cases the
  name but the 'REIT' hint is upper-case, so REITs (e.g. NexPoint Real Estate Finance)
  are not flagged financial.

## Comment attachments (2026-10-26)

Each comment can carry up to 5 files (10 MB each). Bytes live in Cloudflare KV under
`file:<email>:<id>` (the Worker's `PUT/GET/DELETE /api/files/<id>`); a comment stores only
`attachments: [{id, name, size, type}]`. The UI uploads the files first, then saves the
comment, so a failed upload adds nothing. Attaching needs the Cloudflare connection
(button disabled on file:// or when the API is unreachable); deleting a comment deletes its
files. Images show as thumbnails, other files as download links. Export/Import and
`scripts/merge_comments.py` carry the attachment metadata only - the dated KV backups
(`backup:<email>:<date>`) also hold comment metadata but NOT file bytes, so Cloudflare is
the only copy of the attached files. Tested locally with `worker/test_local.mjs`
(Playwright: upload, thumbnail, download headers, >10 MB rejection, reload persistence,
delete cascade) on both pages. The Worker must be redeployed (Cloudflare rebuilds from the
branch on push) before the Attach button works on the live site.

### Research pass on the 45 rescued companies (2026-10-26)
Market caps, corporate-actions screen, theses and gross margins were researched by agents
(WebSearch only) for the 37 Europe + 8 US/Canada companies added by the dilution-stub rule.
- **Market caps**: 36 Europe (Loihde: no 2026 price found, raw-extract value kept) and 8 US written
  to `mc_overrides_applied.json`. Many are aggregator quotes dated Jun-Oct 2026 with approximate FX
  (EUR/USD ~1.14, GBP/USD ~1.33); treat them as indicative until a normal tier refresh. Flagged
  low-confidence: VIM, MANO, TTS, KEYS, FPH (Class A vs A+B), TBL (FX implied by the input file).
- **Corporate actions**: all 45 screened (`*_coverage.json`). Notables: Kenmare (non-binding IRH
  proposal 2026-10-06, deadline 17 Nov), Procimmo (Vaudoise 97.2%, squeeze-out at CHF 9.50 planned,
  delisting not yet confirmed), SMCP (majority holders' sale process led by Lazard), Funko (formal
  strategic review incl. possible sale), Audax (Elmera bid outbid by Fortum).
- **Delisted**: Animalcare (AIM:ANCR) was taken private by Charterhouse (336p, effective 30 Jul 2026,
  delisted 31 Jul) - added to `data/delisted.json`, so hidden from the table (verified on a second search).
- **Distress**: EdiliziAcrobatica (BIT:EDAC) flagged 'warning' (suspension until 7 Sep 2026, FY2025
  loss EUR 17m, debt rescheduled Aug 2026) - verified on a second search. DF Deutsche Forfait
  (first pre-tax loss since 2018, supervisory board lost quorum) and Funko (covenant waivers) are in their
  red-flags text but not flagged.
- **Gross margins**: only 6 Europe + 6 US/Canada found from company releases; no-gross-profit-line
  names (banks/insurers/property/lessors/football club) and `not_found` ones stay on the pool-median
  fallback. SMCP's 75% is the company's own "management gross margin". Candidate (unverified)
  margins in the agents' notes: KMR ~5.6%, KEYS ~25.5%, TAM ~44.5%, VIRSI ~11.1%.
- **Ranks**: Foresight Group #27, SMCP #83 and Purcari #109 enter the top 150; next best is Kenmare #227.

## Asia / Pacific dashboard (started 2026-10-26)

New third market: `docs/asia.html` ("Asia / Pacific" in every page's Market dropdown).
- **Source**: `data-asia/raw/Asia_15m-1B.xls` - Capital IQ screen "Asia / Pacific Developed
  Markets (Primary)", US$15M-1B, 8,237 companies, same 87-column layout as Europe/US.
- **Pipeline**: `scripts/ingest_asia_pool.py` (reuses `ingest_us_pool.build_company` = the same
  7 quality gates incl. the 2026-10-26 IPO-stub dilution rule, and `us_scoring.compute_fixed_pts`)
  -> `data-asia/companies_pool_all.json` (1,895 survivors) and `companies_pool_nonfinancial.json`
  (1,860; the financial flag is a name heuristic). Like USA/Canada, ALL gate survivors form the
  pool (no top-N cut, unlike Europe's top-1,000); research proceeds in tiers by rank.
  80 survivors only pass thanks to the stub rule (flagged `dilutionAdjusted`); Korean share
  series are noisy (splits/restructurings), so treat those with care.
- **Countries**: shown by country of incorporation, except offshore incorporations
  (Cayman/Bermuda/BVI/...), which are shown under their listing market (e.g. Hong Kong);
  the original is kept in `incorporation`. Japan 962, South Korea 555, Hong Kong 167,
  Singapore 110, Australia 78, New Zealand 15.
- **Build**: `scripts/build_site_asia.py` + `site/template_asia.html` (a copy of the US template with
  the Sector toggle); CI rebuilds it with the other two. Data files `data-asia/mc_overrides_applied.json`,
  `corporate_actions*.json`, `distress_flags.json` start empty.
- **State**: quantitative scores only - every company is on the pool-median gross margin
  ("needs GM"), raw-extract market caps, no theses, no corporate-actions screen.
  Comments (shared store) work as on the other pages.

### Asia tier 1 (top 50 at launch, 2026-10-26)
Workflow per tier of 50 (by current all-sector rank, excluding done tickers): agents (WebSearch only)
do market caps + corporate actions (<=3 searches/company), then theses (<=3), then gross margins
(<=2); search budget is shared (~200 per turn), so split into rounds. Merge helpers live in the
session scratchpad (not in the repo): data goes to `data-asia/mc_overrides_applied.json`
(has an extra `quoteDate`), `corporate_actions*.json`, pool files (`thesis`), `gm_research_log.json`.
- Market caps: 49/50 refreshed. Quote dates range Jun-Oct 2026 and FX (esp. KRW) is uncertain -
  indicative only. Echomarketing (A230360): Bain Capital holds ~91% after tenders, share exchange
  planned 15 Jun 2026, delisting likely but unconfirmed -> kept visible with extract mc.
  Hafary: founders' offer S$0.64 (pending). KC Co: PE owner selling. Clinuvel: considering Nasdaq move.
- Delisted: Hyundai Home Shopping (A057050) share-exchange into Hyundai G.F. Holdings (Jun/Jul 2026) ->
  `data-asia/delisted.json`; the Asia page now has the Delisted window (ported from Europe).
- Theses: 50/50 (minus HHS deleted/kept). Holder percentages are mostly aggregator-sourced and
  websites for 33 were dropped (guessed). Logen (A033290) identity unclear; PRL Global revenue in the extract
  looks inconsistent with sourced segment data - check.
- Gross margins: 24/48 applied (9 verified from announcements/IR tables, 15 aggregator revenue+cost
  lines, flagged unverified); eSang (low confidence) and Shinsegae Information (sources disagree) skipped;
  the rest not found (DART largely unreachable via search). Until more GMs are known the pool-median
  GM fallback is the median of these 24, skewed to low-margin names.
- localStorage keys on the Asia page are namespaced `shortlist_asia_*` (comments key stays shared).
