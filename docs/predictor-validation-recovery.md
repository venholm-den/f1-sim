# Predictor validation recovery, 24 October 2026

## Implemented

The enabled prospective suite was invalid after source merges: nine pinned
files differed. `scripts.prediction_trials --renew-existing` now registers a
separate cohort with current source hashes, the predecessor's arms and input
archives, and the carried inspection ledger. It preserves the old suite and
backs up the active configuration. This is a new experiment version, not a
repair of old prediction timestamps or a continuation of their sample count.

`--verify-only` checks the current suite without fetching, posting, capturing
or writing a report. Comparison reports also expose invalid suite sources.
Renewal refuses altered predecessor inputs or a different ensemble. Capture
and scoring retain their normal strict checks.

`src/inspection_ledger.py` reads race identities from tuning holdouts,
inspection lists, nested training metrics and calibration splits. Tuning and
suite registration automatically include existing evidence in the known
local output folders. Reports saved elsewhere must be supplied explicitly with
`--inspected-reports`. Feature ablations use the same field parser.

The old tuning reader omitted its own `holdout_races_evaluated` field and
`inspected_races`. All 23 of its 2024 holdout races were already in the earlier
trial suite's ledger. The three saved tuning runs remain unchanged; a separate
audit records zero fresh races available when reusing any of them. Their
historical scores remain useful diagnostics, not fresh confirmation.

## Local collection verified

The replacement suite is
`outputs/prediction_trials/suites/20261024T150828665558Z_d7254bda/suite.json`,
SHA-256 `b07f85eeaaead705d25bd53af7769b64d3f6aff52ecaf6c588184ad4313a75f3`.
It retains `stage_blend`, `stronger_grid`, `single_pace` and `grid_influence`,
with the same seeds, simulation budgets and promotion rules. Its ledger
contains 130 inspected races. The prior suite and its captures are preserved.

A new source forecast was frozen outside the scheduled app-run directory and
captured as a US FP2 trial in this cohort. Nothing was uploaded to Discord.
The capture correctly records 59.1% matched FP2 long-run coverage, below the
60% component threshold, and falls back to simulation for that component.
This proves capture works with current source, not that a candidate is more
accurate. There are no scored fresh race-stage outcomes yet. The existing
scheduled task remains enabled and unchanged; subsequent hourly execution
has not been asserted from this manual capture.

## Fixed degradation experiment

`scripts.benchmark_degradation_stages` compares only `legacy` and
`single_degradation_v1`, with the declared multiplier 2.0. It reads the
checksum-verified desktop archive, fits no settings, and uses two earlier
races as pace history, 5,000 simulations per seed and seeds 42/123/777.
Development is 2021–2024; 2025–2026 is previously inspected diagnostic data.
All driver episodes are matched. Original archives and forecasts are unchanged.

| Later diagnostic stage | Matched races | Established MAE | Single degradation MAE | Reduction in MAE + top-10 Brier |
| --- | ---: | ---: | ---: | ---: |
| PRE | 30 | 4.277 | 4.048 | 5.42% |
| FP2 | 26 | 4.224 | 3.861 | 8.66% |
| Q | 35 | 3.775 | 3.506 | 7.13% |

No win, podium, top-10 or DNF Brier regressed on those stage aggregates.
Qualifying order still achieves Q MAE **3.304**, beating the candidate's
**3.506**. PRE and FP2 pass historical screening; Q fails the baseline rule.
There are 94 skipped race-stage attempts and ten archive-load exclusions;
their reasons and input coverage are retained. These counts must not be
treated as complete coverage of every season or weather regime.

Decision: keep degradation experimental. These diagnostics do not authorize
live activation or freezing a combined challenger. Next research should
isolate how degradation correction interacts with grid trust, then choose
one probability-focused challenger on development data. Declare its RPS
primary metric and win/podium/top-10/error guardrails before fresh collection.
Do not change the existing cohort's objective or source hashes in place.
Pace uncertainty remains a separate experimental direction; no new strength
or shrinkage parameter was selected by this work.

## Reproduction and evidence

Run in `C:\code_project\f1-sim` with the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m scripts.prediction_trials --verify-only
.\.venv\Scripts\python.exe -m scripts.audit_prediction_evidence --output-dir outputs/predictor_review/NEW_AUDIT
.\.venv\Scripts\python.exe -m scripts.benchmark_degradation_stages --workspace "$env:LOCALAPPDATA\RaceWorkbench" --output-dir outputs/predictor_review/NEW_DEGRADATION
```

New output directories are required; prior artifacts are never overwritten.
Local evidence is under `outputs/predictor_review/20261024-ledger-audit`,
`20261024-degradation-stages` and `20261024-fresh-source`. The replay report
SHA-256 is `59ec7a27c326df7eee4e738060863e740791a4e48713678c9e7539bacd1d7602`.
`screening.json` contains the stage decisions including the Q baseline failure.
The replay ran before adding the screening presentation helper; its source
fingerprints identify that execution. Scoring and model settings were unchanged.

Validation: the final full Python suite passed 818 tests, including the new
diagnostic-screen test. All six JavaScript tests passed. Existing
deprecation warnings remain. No packages were installed, live predictor
defaults changed, credentials edited, Discord messages sent, or binaries
rebuilt. Protected-file checks found only the intended active-suite pointer
change; frozen forecasts, prior trial records, receipts and the unrelated FIA
CSV retained their original hashes.
