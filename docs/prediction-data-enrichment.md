# Prediction data enrichment

The acquisition pipeline writes a new dataset directory. Existing archives,
frozen forecasts, receipts, reference indexes and active models are preserved.
No data download or training run promotes a model.

## Use it in the app

Download detailed Q and R sessions in Historical Data. Add FP2 for recent
seasons; FP1/FP3 are optional additional evidence. Full telemetry is optional.
In Model Training, select **Include practice long runs and recent reliability
(experimental)**. Each run snapshots eligible source tables and saves a separate
inactive candidate. The report shows how many training and validation rows
actually have each input. Restart the source app to load changed Python code;
existing packaged executables need a separate rebuild.

Practice comparisons require accurate green-flag sustained runs, common dry
tyre compounds and comparable session-time buckets. Race-control UTC timestamps
must establish that practice preceded Q. Missing evidence excludes the practice
session. This excludes FP2 after Friday Q on older sprint weekends. The observed
stint trend includes fuel burn, track evolution and tyre effects; it is not pure
tyre degradation. Traffic and fuel loads remain unobserved. Missing practice is
not filled with a fabricated pace estimate.

Reliability features use only earlier rounds in the same season. Known outcome
counts and smoothed driver/team rates are included; Beta(1,9) is an explicit
experimental regularisation assumption. Unknown causes stay unknown. Optional
confirmed causes at `data/prediction_enrichment/retirement_causes.csv` are
snapshotted by enriched app training. Their publication time must precede the
target qualifying cutoff before they enter earlier-race reliability history.
Suspected causes must not be entered as confirmed. The supplied one-row seed
corroborates Alonso's 2021 Bahrain brake retirement; it does not establish an
intrinsic manufacturer reliability problem.

## Reproducible dataset build

Run from the main checkout with its existing virtual environment. Use a new
output directory for each run. No additional packages are installed.

```powershell
.\.venv\Scripts\python.exe -m scripts.build_prediction_data `
  --workspace "$env:LOCALAPPDATA/RaceWorkbench" `
  --years 2021 2022 2023 2024 2025 2026 `
  --output outputs/prediction_data/new-snapshot `
  --refresh-race-timing 2 `
  --retirement-causes data/prediction_enrichment/retirement_causes.csv
```

The builder checks archive hashes and event identity, exports source tables,
practice features, descriptive retirement/strategy datasets, venue identities,
coverage gaps and output checksums. Telemetry is not bulk copied. UTC observation
times can be recovered from an already-downloaded car trace's Date minus
SessionTime, provided the origin is stable; Time alone is never used for this.
Absent sessions can mean either missing downloads or a sprint format without
that practice session. `--cached-practice N` tries a bounded number of missing FP2
sessions from the local cache only; the Historical Data page downloads uncached
sessions. Cache-only timing refresh does not replace archive versions.

## FIA PDFs

Add `--collect-fia --pdf-python <existing-PDF-capable-python> --max-documents 100`.
The optional worker needs pdfplumber in that interpreter, not in the app venv.
The installed Codex workspace runtime provides it on this machine. Source PDFs,
extracted text, publication times, hashes and errors are retained. Separate
`entries.csv`, `grids.csv` and `grid_penalties.csv` contain extracted data.
Narrative penalty, power-unit and tyre documents remain review evidence.

Complete grid/list identities are checked against the archived Q roster.
Sprint grids, incomplete lists, unknown drivers and unsupported pit-lane layouts
are rejected. Explicit supported pit-lane entries have GridPosition=0 and a
separate flag. Qualifying roster mapping is retrospective evidence, not proof of
an independently captured PRE entry list. No scraped file is silently installed
as a live FIA index or live roster.

`asof_grid` selects one complete publication version at a timezone-aware cutoff;
it never combines revisions or admits an undated grid. CET and CEST labels are
interpreted literally, with the raw publication string retained in collection
metadata. Final Sunday grids cannot enter a Saturday-Q forecast. Grid footnotes
provide explicit penalty records; narrative mentions never automatically apply
penalties. `reparse_cached` evaluates saved extraction data into a new folder
without new downloads. Raw PDFs remain the review authority.

## Original weather forecasts and start delays

`--weather-requests requests.csv` accepts Year, Round, Event, CircuitId, LayoutId,
Latitude, Longitude, RunUtc, CutoffUtc and ScheduledStartUtc. Model is optional.
Coordinates must match saved physical venue evidence, so a relocated Bahrain
event cannot accidentally request Sakhir weather when its venue is Sepang.
Original-run responses and four conditional start windows are saved. The API
requires the original run horizon rather than start_hour/end_hour parameters.

Initialisation time is not public-availability time. A replay is training-eligible
only with complete windows, ArchiveKind=original_operational, a sourced
RunAvailableAtUtc no later than CutoffUtc, and AvailabilitySourceURL. Hindcasts
and unverified availability are excluded. Temperature/wind validation pairs use
actual UTC observation times. Binary Rainfall is not treated as rainfall amounts.
These archives are not automatically fed to the historical model or live sim.

`--delay-labels labels.csv` requires Year, Round, Event, ScheduledStartUtc,
ActualStartUtc, StartDefinition, Reason, SourceURL and Verified. StartDefinition
must be formation_lap, lights_out or rolling_start, consistently applied to both
timestamps. Normal starts require Reason=normal and zero delay. Missing events
never imply normal starts. Aborted starts and later red-flag restarts must not be
confused with the initial formation lap. Race-control keyword matches form an
unverified review queue only. The initial sourced examples are positive cases;
normal controls and broader coverage are still needed to fit delay probabilities.

Pit crossing times produce measured pit-lane traversal, separated by green,
SC/VSC and red-flag conditions. This includes stationary time and is not total
time lost versus staying on track. Older archives without crossing times retain
unknown values; new downloads preserve crossings and session-status records.
Target-race stints, pit measurements, weather and delays are descriptive labels,
not current-race training predictors.

## Validation

Use `scripts.train_historical_model --historical-dir <snapshot> --model-dir
<new-candidate> --enriched` for offline comparison. Predictor selection and
preprocessing are fitted on training races only. Later whole races are held out.
Compare with an otherwise identical qualifying-only candidate and grid-order
baseline. Previously inspected holdouts remain diagnostic; they cannot establish
an independent accuracy gain or justify activation.
