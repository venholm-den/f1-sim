# FIA index refresh and verified grid inputs

The existing hourly Windows task runs `scripts.auto_forecast` from the main checkout. It now refreshes FIA documents before checking forecast eligibility, including when a forecast for the session already exists. `--check-only` does not refresh or post. The collector shares the Simulation Centre workspace lock and isolates collection failures from forecasting and post-race scoring.

Local opt-in configuration is `config/fia_sync.json` (ignored); copy `config/fia_sync.example.json` on another machine. This PC is enabled with an existing bundled Python containing pdfplumber. No packages are installed at runtime. If the PDF runtime disappears, document metadata remains available and extraction is reported for review. `pypdf` is an optional fallback with fewer layout capabilities.

Normal checks are hourly, with a ten-minute failure throttle and a maximum of 24 PDFs / 100 seconds of enrichment per invocation. The season landing page supplies the latest event. Grids are rechecked on every due invocation; unchanged other PDFs are checked again after six hours. Unprocessed documents continue on later runs. A quiet offseason still performs a bounded check. New FIA season URL identifiers must be configured in `FIA_F1_SEASON_IDS` when the publisher creates them.

Manual refresh, without Discord:

```powershell
.\.venv\Scripts\python.exe -m scripts.refresh_fia_documents --year 2026
```

Add `--all-events` to scan the season's event listings; PDF enrichment remains bounded. This does not promise that every historical PDF will be decoded in one run. Past season metadata is retained when refreshing the current event.

Each capture under `data/fia_documents/captures` retains the listing, index before/after, and report. PDFs and extracted JSON are content-addressed under `data/fia_documents/cache`. CSV replacement is atomic. `sync_state.json` records the last attempt and per-document outcomes. Raw evidence, unsupported layouts, and missing identities remain available for review.

## Extraction and model use

- Complete race grids require names and car numbers to match the same event's cached pre-race roster. No future race result is loaded to establish identity.
- Staggered columns, explicit pit-lane sections, withdrawals, and optional entry-list abbreviations are supported. Car-number superscripts are removed only when PDF geometry verifies the smaller raised digits; arbitrary numbers are never truncated to fit a roster.
- Sanctions come from the explicit **Decision** field or grid footnotes. Narrative reasons and summons do not impose a sanction. “No penalty” is retained as a decision, not counted as a race grid penalty. Sprint targets are kept separate.
- A numeric drop is not added to qualifying position. The FIA's complete published grid determines placement, including large penalties and multiple penalised drivers. Duplicate grid footnotes and their source decision are deduplicated.
- Every live context requires both publication and first-observation timestamps before the run cutoff. Undated, recalled, incomplete, or ambiguous revisions are excluded. A newer unsupported grid blocks fallback to an older grid. Historical replay cannot use documents first captured today as if they had been captured before that race.
- A grid must match the complete model roster before it overrides qualifying. Pit-lane entrants are approximated behind the last grid starter by the current simulation; a dedicated pit-lane time-loss model is still needed. Withdrawals are extracted explicitly but are not applied to a simulator that has no DNS model; grid selection falls back and the raw status remains in the FIA context.
- Decisions recorded before a complete revised grid are explanatory evidence only. Carry-over penalties to another event are not guessed. They take effect through that event's official grid.

`fia_context.json` records the exact cutoff and selected evidence. New automated snapshots include and hash this packet. Driver explanations include available FIA decision text and flag sanctions whose placement has not yet been confirmed.

An existing frozen forecast is never rewritten. Before reusing a completed
session, automation now compares its saved grid with the latest complete,
publication-aware FIA race grid for the exact roster. A changed starting order
or pit-lane status before race start creates a separate forecast with a fresh
cutoff and a link to the superseded run. The completed revision must prove that
every driver used the promised FIA grid. An unchanged order does not rerun.
Incomplete, unsupported, post-race or roster-mismatched grids do not trigger
revisions. The normal opt-in delivery policy still applies; delivery receipts
on prior forecasts are preserved. `--check-only` reports `grid_update_ready`
without creating a run or posting.

Desktop results warn when a newer verified grid differs from the saved forecast.
They do not silently combine updated grid labels with old probabilities. The
tyre page labels a revised run's positions as FIA grid, and Follow PC runs picks
up the new completed revision. Older executables require the new build.

## Desktop reference updates

The updated desktop app merges the PC checkout's FIA index into its managed AppData index while **Follow PC runs** is enabled, even when no new forecast has completed. It checks on the normal 15-second PC poll, before previews and before manual simulations. The PC collector still determines when new FIA publications are fetched.

Each replacement preserves the previous CSV under `data/fia_documents/sync_backups` and records a receipt in `outputs/fia_reference_sync.json`. Additional local document rows are retained. Custom source paths and files with custom columns are left untouched, and disabling Follow PC runs stops the merge.

The FIA preview sorts all records by parsed publication time, newest first, before pagination; undated records appear last. Publication date is the first visible column. Manual reloads and newly synchronized data return the FIA preview to page one; routine background validation preserves the current page.

## Validation on 11 October 2026

The current Singapore refresh added 73 listings and extracted all 22 grid drivers and 22 entry-list drivers. The published grid includes Russell in P21 and the explicit decision records a 40-place drop. The Sprint pit-lane decision for Sainz is not a Sunday grid adjustment.

On the same 100 saved historical PDFs, the previous extractor accepted 80; the revised extractor accepts 88. Grid rows increased from 1,016 to 1,206. Nine Sprint grids are intentionally excluded and three documents remain quarantined. Historical replay outputs are separate under `outputs/fia_refresh/20261011/historical_reparse_v2`; they do not rewrite historical prediction snapshots or establish improved predictive accuracy.
