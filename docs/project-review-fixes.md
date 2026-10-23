# Project review fixes - 11 October 2026

Implemented in the canonical source checkout, C:/code_project/f1-sim.

## Recovery and versioning

The pre-change source and tracked reference data are recoverable from local branch
`codex/review-baseline-20261011t024954z` (commit
`ae653cab82ddc6c01f2ba415a752dfe09a54d0b9`). Its Git bundle and the protected-file
hash ledger are under `outputs/reviews/review-fixes-20261011T024954Z`.
The current branch and staging area were not changed. Generated untracked
prediction-enrichment/recent-baseline archives remain local, outside the source
checkpoint; their excluded paths are recorded in checkpoint.json.

## Changes

- Historical CSV merges reject unreadable existing archives. Serialization uses
  a unique sibling temporary file and atomic replacement; a failed replacement
  retains both the original archive and the staged recovery file.
- Application startup/history flag malformed job records as unreadable, retaining
  the original bytes. Valid jobs remain available.
- Race Setup now uses the same managed child-process lifecycle as Simulation
  Centre. Run configuration, log and job status are durable. Closing the window
  cancels an active manual worker and records cancellation before shutdown.
  Failed/cancelled runs retain partial output without completion metadata.
- Scheduled runs write `outputs/automation/last_health.json`. Core scoring or
  delivery failures return exit code 1. Pending official results and deliveries
  waiting for backoff return zero with an explicit waiting state. Uncertain
  delivery requires review and is never automatically resent. Optional collection
  and experimental failures produce warnings without blocking the live forecast.
  Check-only still does not write the health report or deliver anything.
- Dated PRE entry lists require `ExpectedEntrants` on each row. The count must be
  consistent, integral, and match the selected complete version. Counts must come
  from entry-list evidence, not be inferred from the number of downloaded rows.
  Older lists without this completeness declaration fail explicitly; no permanent
  field size is hard-coded. Without an eligible list, the labelled baseline-roster
  assumption remains available.
- New summaries expose `top10_chance` and `points_scoring_chance`. The historical
  `points_chance` field remains a compatibility alias for top-ten probability.
  Points-scoring probability measures simulated points greater than zero.
  Charts, report text and score labels identify the legacy target as Top 10.
  Existing frozen predictions and evaluation targets are unchanged.
- New snapshots include Python/platform/package versions and hashes of available
  Python sources, main.py and requirements.txt. Version is 0.2.0-beta.2. Future
  builds include the orchestration sources needed for this metadata. Old manifests
  remain valid without the new metadata; local hashes are still not trusted dates.
- CI runs Python and existing JavaScript tests on Linux and Windows. Syntax checks
  include main.py, scripts and portable_app. A real offline worker regression uses
  a separate disposable workspace; loopback-origin/token checks are covered by
  the existing server test. Hosted CI has not been executed from this checkout.
- Architecture documentation now distinguishes the current Python/pywebview UI
  from the proposed Rust/React/Tauri direction.

## Experimental comparisons

The source checksum changed, so the enabled local prediction comparison has a
new versioned registration. It preserves the same inactive ensemble, variants,
seeds, simulation counts and promotion gates, carrying forward the prior suite's
inspected-race ledger. The previous suite and configuration backup are preserved.
Existing forecasts from an earlier simulation-source version still fail closed
when exact-source replay is required; they are not rewritten or relabelled as
fresh validation. No model was fitted, activated or promoted.

## Verification and limits

- 502 Python tests passed, including new archive, metadata, entry-list, health,
  probability-semantics, cancellation, provenance and actual worker regressions.
- 6 JavaScript tests passed; syntax compilation and pip check passed.
- A seeded comparison with the checkpoint's simulator produced identical legacy
  summary columns, raw simulation rows and position matrices. Only the two new
  explicitly named probability columns were added.
- All 78 pre-recorded protected files (frozen forecasts, delivery receipts and
  environment files) retained their exact SHA-256 digests.

No Discord deliveries, model-accuracy claims, GitHub pushes, package rebuilds or
MATLAB runs were performed. Existing executables remain unchanged and require a
separate build/acceptance check. Forecast skill still requires fresh prospective
validation. Broader strategy-module decomposition remains incremental work;
these fixes extract health/provenance services and reuse the worker lifecycle
without changing the model architecture.
