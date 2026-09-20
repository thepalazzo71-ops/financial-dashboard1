# Dashboard backup

`index.html` is a point-in-time backup of the live dashboard's source,
captured 2026-09-20 from https://claude.ai/artifact/WJD9KPY74x2MpxwATWixka.

It is a static snapshot: the ~1,000-company financial dataset is baked in
as of the capture date, and it does **not** connect to the live `overrides`
db collection (opening it standalone will show the stats as of capture,
with a notice that edits aren't being persisted). It exists so the
dashboard's code (layout, scoring/sorting logic, snapshot/update UI) isn't
solely dependent on the Artifact platform — if the hosted version is ever
lost, this file is what you'd re-publish from.

This file is not auto-synced with the live artifact. Re-capture it (ask
Claude to read the artifact and save a fresh copy here) after any
significant change to the dashboard's code, not after routine data-only
updates (those are tracked in `data/` and `snapshots/` instead).
