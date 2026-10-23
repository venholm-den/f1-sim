# Race Workbench: Windows beta 0.2.0-beta.1

An experimental local-first race forecasting app. This is a private testing
candidate, not yet a signed or publicly published release. No central service,
accounts, telemetry uploads, subscription, or auto-updater is included.

## Launch

The full dashboard resolves event/session labels from saved outputs, rather than
labelling old results with newly selected setup. Its saved-run health panel shows
lap/model driver coverage, duplicates, clean laps, session completion, telemetry
status, saved-file age and recorded selection/grid assumptions. Saved-file age is
not proof of upstream cache freshness. Telemetry failures can be retried with
Refresh outputs and are distinct from missing event context or coordinates.

Weather observations and model weather multipliers are persisted for new runs in
`weather_context.json`. Simulated red-flag risk is not a weather forecast; absent
rain probabilities remain unknown. Older outputs are not rewritten to fabricate
weather observations.

1. Extract the **entire** release ZIP into a folder, including `_internal`.
2. Double-click the `.exe` whose name matches the extracted release folder.
3. Race Setup opens with the rebuilt workbench interface. Select the race/session,
   choose your output switches and click **Run simulation**. Results are written
   into a fresh `workbench_runs` subfolder under the selected output directory.
4. Open **Results**, **Data Sources** or **Compare** to inspect the saved data.
5. For **Forecast next race**, post-race scoring, Discord or Simulink, open
   **Simulation Centre** from the sidebar. The next-race forecast selects eligible
   inputs and runs 10,000 simulations by default.

The package includes `FUNCTIONALITY.md` describing the working controls and model
features still missing from the mockups. Confidence and safety-car probabilities
are explicitly unavailable; no illustrative mockup values are used as model data.

**Historical Data** builds a local archive for selected seasons/ranges. Detailed
timing data starts in 2018; classifications start in 1950. Downloads can be stopped
and resumed, and saved seasons can be previewed/exported. See `HISTORICAL-DATA.md`.

### Optional Discord upload

Select a completed frozen forecast and choose **Upload report to Discord**.
Confirm the prompt to send the forecast CSV and all available charts. Reports
over ten attachments are split into messages; receipts prevent duplicate sends.
New forecasts generate the full chart bundle locally, including fantasy value
when price data is available. Older forecasts only upload files they already
contain; they are never rewritten to add charts.

The webhook stays in the local workspace's `.env.discord` file as
`DISCORD_WEBHOOK_URL`. It is never bundled into the EXE or returned to the UI.
Source runs can also use their existing `.env.automation` or `.env` configuration.
Forecasting alone does not upload anything; the hourly source automation remains
separate and keeps its existing opt-in upload setting.

Python and MATLAB are not needed for the packaged probability forecast.
The desktop window requires Microsoft Edge WebView2. If its runtime is absent,
use the executable with `--browser` to open the local interface in your browser.
Internet is needed for new data; saved results can be reviewed offline.
The executable is currently unsigned; do not disable Windows security controls
to run an untrusted copy. Clean-machine compatibility is still a release gate.

User settings, caches and runs live in `%LOCALAPPDATA%\RaceWorkbench`, separately
from the extracted program. Extracting a newer version does not overwrite them.
Back up that folder to preserve your history. The source launcher continues to
use its repository workspace, so its history is intentionally separate.
An explicit `--workspace "C:\path\to\workspace"` selects another local workspace.
Use `--simulation-centre` to open the forecasting tools directly.

## Forecasts and honest evaluation

The next-race mode records its local UTC cutoff and target race start. It uses
qualifying when eligible, otherwise the latest eligible weekend session or PRE
before practice. Eligibility checks finalised/ended status and usable lap/driver
data first, allowing completed sessions immediately. Known live or data-empty
sessions are excluded. A scheduled-start-plus-three-hour buffer is only a fallback
when readiness cannot be checked; missing pipeline data still fails visibly. The forecast pipeline
is given an explicit allowlist of those weekend sessions, excluding the race.

It uses two earlier races as baseline inputs and one prior strategy season.
Trained historical calibration and live forecast weather modifiers are disabled.
Before practice, roster/grid assumptions come from the existing model; they are
not a confirmed entry list or starting grid. Pit strategy may be unavailable.
The result is experimental and has not established predictive calibration.

Each successful run reserves a new `frozen` folder containing forecast results,
features, config and a SHA-256 manifest with model-source fingerprints. The app
will not overwrite it and checks its files before scoring/exporting. A forecast
that finishes after the race starts is not frozen as a pre-race prediction.
These are local write-once snapshots, **not trusted server timestamps**: someone
with filesystem access can change both files and hashes or their system clock.

After the race, select a frozen forecast and click **Score against race results**.
Scoring opens eight hours after the scheduled start and requires a finished
session with FastF1 result classifications and matching driver coverage.
It saves a separate evaluation with actual positions, finish-position MAE and
win/podium/top-ten Brier scores (mean squared probability error). Lower is better;
the top-ten score is a finishing-position proxy, not adjudicated points eligibility
for shortened or exceptional races. Results may change following penalties;
rerun evaluation to save a new dated version without replacing the original.

Historical replays remain separate and may use later weekend information/current
reference tables. They are **not leakage-free historical forecasts**, and cannot
be counted as prospective submissions merely because a race is now in the past.

## Optional sharing foundation

**Export sharing preview** writes a reviewable JSON into the run's `exports`
folder. It includes event/cutoff, probabilities, simulation settings and hashes;
it excludes local paths, raw logs, credentials and user identities. Nothing is
transmitted. Inspect it before sharing it yourself.

A later opt-in service should provide server receipt timestamps, versioned
schemas, input/model fingerprints, duplicate detection, retention/deletion
controls, and separate prospective/retrospective results. Compare models against
simple baselines and score across many races. Many repetitions of identical
inputs/model assumptions reduce sampling noise; they do not remove model bias.
Do not present repeated seeds as independent community predictions.

## Advanced modes

Monte Carlo from saved inputs, historical downloads, and result exports remain
available. Lap dynamics and scenario experiments require a separately installed,
licensed MATLAB with Simulink. MATLAB is not redistributed in this package.
See `docs/simulation-centre.md` in the repository for the research workflow.

## Build and acceptance

From the repository, using its configured Python environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\scripts\build_portable_app.ps1
.\.venv\Scripts\python.exe -m scripts.smoke_beta_package .\dist\RaceWorkbenchBeta-0.2.0-beta.1-r2\RaceWorkbenchBeta-0.2.0-beta.1-r2.exe
```

The build refuses to overwrite an existing release; choose a new `-Name` when
rebuilding. The smoke test uses a fresh isolated data folder under
`outputs/beta_acceptance`, runs the actual packaged EXE and writes its acceptance
JSON. It downloads data and is a runtime test on the current computer, **not** a
clean Windows VM or an accuracy test.

Before public distribution: clean Windows testing without Python/MATLAB,
dependency notices and redistribution review, upstream data-use/branding review,
signed release/download provenance, accessible native UI QA, and a documented
update/support policy. Shared hosting is a separate decision and is not enabled.
