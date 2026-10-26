# Protected local forecast runtime

Development remains in `C:\code_project\f1-sim`. Scheduled forecasts can run
from a separately named source snapshot under `C:\code_project\f1-sim-runtimes`.
This prevents ordinary checkout edits and merges from changing the scheduled
model or invalidating its source-pinned shadow suite.

Each snapshot copies tracked code/resources and explicitly selected local
control JSON files. It shares `data` and `outputs` with the original workspace
through Windows directory junctions. Existing frozen forecasts, receipt paths,
locks, archives and duplicate-delivery decisions therefore remain in place.
No credentials or archives are copied. The task selects the original ignored
environment file by absolute path.

`scripts.forecast_runtime` verifies source/resource/config hashes, installed
dependency versions, the interpreter, shared directory targets and the enabled
prediction suite before importing the hourly automation. Edited code, added
modules, changed control files or dependency drift cause a nonzero exit before
any collection or delivery. Data and output files are intentionally mutable;
their existing snapshot/suite checks still apply. This is accidental-change
protection, not a security boundary against someone who can edit the manifest.

## Prepare a new version

First run the Python and JavaScript regressions in the development checkout.
Review source changes and consolidate previously inspected race identities,
including completed shadow scores and archive replays, in an append-only JSON
report with an `inspected_races` field. Never call these outcomes fresh.

```powershell
.\scripts\prepare_forecast_runtime.ps1 `
  -RuntimePath C:\code_project\f1-sim-runtimes\NEW_VERSION `
  -InspectionReport C:\code_project\f1-sim\outputs\baseline_recovery\NEW_AUDIT\inspection.json
```

The script refuses an existing destination. It registers a successor of the
four-arm suite using the same ensemble, grid mappings, seeds and budgets. The
old suite/captures remain immutable; the new cohort starts at zero scored
races. This does not promote a model or combine the cohorts' sample counts.
The predecessor configuration is retained in `outputs/prediction_trials/config_backups`.
An invalid independent form/risk suite remains blocked pending its own source
benchmark; this preparation does not bypass that separate registration gate.

Seal verification and a read-only eligibility check, from the new runtime:

```powershell
C:\code_project\f1-sim\.venv\Scripts\python.exe -m scripts.forecast_runtime verify
C:\code_project\f1-sim\.venv\Scripts\python.exe -m scripts.forecast_runtime run `
  --env-file C:\code_project\f1-sim\.env.automation --check-only
```

The interpreter/environment is shared with development to avoid reinstalling
packages. Its installed dependency versions are sealed and checked at every
run, so upgrades require a deliberately tested new runtime. The snapshot does
not protect against edits made while an already-running process is importing
code. Treat sealed folders as immutable; use a new version for every change.

## Scheduled task deployment and rollback

Before changing routing, export the current task XML and record its state,
action, triggers, settings and principal. Do not interrupt a running task.
Preserve the existing trigger, user, schedule, simulation count and posting
options. Change only the action's working directory and module:

```text
Execute: C:\code_project\f1-sim\.venv\Scripts\python.exe
WorkingDirectory: C:\code_project\f1-sim-runtimes\NEW_VERSION
Arguments: -m scripts.forecast_runtime run --n-sims 100000 --discord --env-file C:\code_project\f1-sim\.env.automation --post-race --weekend-briefing
```

These posting options reflect the existing local task; they are not defaults
for a new installation. Re-read the action and verify all other task fields
against the export. Do not manually run an upload to test routing. A later
scheduled result is operational evidence distinct from the read-only check.

Rollback restores the previous action, recorded alongside the exported XML,
without deleting the new snapshot or modifying frozen evidence. Restore a
matching backed-up suite pointer if returning to an earlier protected runtime;
never edit a suite's source hashes in place.

Keep the development suite pointer aligned with the runtime's new pointer
after deployment, backing up the prior file. Later development may invalidate
the checkout's own suite read without invalidating scheduled collection; use
the protected runtime's verification command for its actual status.
