# European Small/Mid-Cap Value Shortlist

A value-investing dashboard that screens ~6,109 raw European small/mid-cap
companies (US$15M–1B market cap) down to a ranked top-150 shortlist using a
documented 9-dimension scoring system ("v6"), and keeps that shortlist live
by periodically refreshing market caps (and eventually gross margins) for
the companies in it.

Full background, the scoring model, the refresh workflow, and open items
are in [`docs/handoff-brief.md`](docs/handoff-brief.md) — read that first.

## Dashboard

Live at **https://claude.ai/artifact/WJD9KPY74x2MpxwATWixka**.

- Static financial data for the 1,000-company scored pool is embedded in
  the page's HTML at build time.
- Market-cap (and future gross-margin) overrides live in the artifact's
  `db` capability, collections `overrides` (keyed by ticker) and
  `gmOverrides` (not yet used). The page has a live `onSnapshot`
  subscription, so writes show up without a reload.
- As of this repo's setup: **68 of 150** shortlist companies have a
  refreshed market cap in the `overrides` collection (verified live against
  `data/mc_overrides_applied.json`, which mirrors it).

## Repo layout

```
data/
  companies_1000_scored.json   the fully-scored 1,000-company pool (v6 model)
  mc_overrides_applied.json    ticker -> current market cap ($M), mirrors the
                                dashboard's `overrides` db collection
docs/
  handoff-brief.md             project background, scoring model, workflow, progress
scripts/
  snapshot.py                  regenerates a dated .xlsx snapshot from data/
snapshots/
  shortlist_snapshot_*.xlsx    dated historical snapshots (one per update, see workflow)
```

Not yet in the repo (need to be re-sourced — see handoff brief): the raw
Capital IQ extract (`Europe_15m-1B.xls`), the methodology write-up
(`European_Shortlist_Methodology.docx`), the prior AI-run reference file,
and the gross-margin research spreadsheet.

## Workflow

Every market-cap (or gross-margin) update to the dashboard should:

1. Update `data/mc_overrides_applied.json` (or a future
   `data/gm_overrides_applied.json`) with the new values.
2. Run `python3 scripts/snapshot.py` to generate a dated snapshot into
   `snapshots/` *before* writing to the dashboard.
3. Write the batch to the dashboard's `overrides` (or `gmOverrides`)
   collection.
4. Commit `data/` + the new `snapshots/*.xlsx` file.

Setup: `pip install -r requirements.txt`.

## Source-rule constraints

Gross-margin research must come only from company-published documents and
exchange filings (annual reports, IR pages, earnings releases, exchange
filings) — no third-party aggregators. No manual additions or removals to
the final ranked list; if a company is missed, refine the model instead.
See `docs/handoff-brief.md` for the full detail and the one standing
exception (Card Factory).
