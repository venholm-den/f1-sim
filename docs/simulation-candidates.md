# Simulation candidates - 11 October 2026

These experiments run locally and remain unpromoted. The default source run,
scheduled configuration, frozen forecasts, trained live models and Discord
destination are unchanged. Candidate configurations reject Discord posting.
Use the existing `.venv`, from `C:\code_project\f1-sim`.

Copy `config/simulation_candidates.example.json`, choose a new output directory
and the intended upcoming event, then run `main.py --config YOUR_CONFIG.json
--no-discord`. The CLI override also neutralises an inherited dotenv delivery
preference. Enable one candidate at a time for interpretable comparisons.

## Race-window weather

Set `model.weather_model` to `race_window_v1`. The run targets the event's
explicit UTC **Race** schedule field, never the input qualifying/practice date.
It captures regional best-match and ensemble guidance using the existing
Open-Meteo collector, saves the raw/report packet, and passes the scheduled
best-match window to the simulation. Qualifying observations and race-control
hints are not reused as Sunday weather. Missing weather retains unknown rain
and neutral modifiers; invalid schedule/venue/availability fails closed.

For replay, set `model.race_weather_report_path` to a saved `race_weather.json`
beside its `race_weather_raw.json`, and set an explicit timezone-aware
`run.feature_cutoff_utc`. Raw checksums and availability times must agree;
the capture must be available by that cutoff, before the race start. A new
capture cannot be used to reconstruct an earlier forecast. Current forecasts
cannot supply historical weather accuracy evidence.

The main candidate uses deterministic best-match guidance, not a calibrated
wet-track probability. `scripts.race_weather_shadow` remains available for
coherent ensemble-member/delayed-start sensitivity. Intra-race showers, wet
tyre transitions, drainage, standing water and start decisions remain absent.

## Qualifying-anchored partial-pooling pace

`qualifying_partial_pooling_v1` is a small Gaussian Bayesian regression, fitted
only on strictly earlier Q/race pairs, excluding races with observed rain.
The response is an observed clean
race pace gap in percent of lap time. Predictors are official Q rank, available
Q timing and timing missingness, with shrunk driver/team effects and circuit-
specific Q-to-race slopes. Shared posterior coefficient draws preserve
covariance; unseen groups retain prior uncertainty. Declared priors and a
0.5 percentage-point observation SD are assumptions, not tuned accuracy gains.
Fuel, tyre wear, traffic and track evolution remain partly confounded.

**Cached Q Position values can be entirely missing.** The old grid benchmark
then uses its existing timing-derived fallback. Such runs must not be described
as using official qualifying order. The new pace model requires a complete
official classification and never manufactures one from fastest laps.

An optional `--qualifying-results` accepts an explicit Q classification CSV
or the saved `historical_library` directory. Library version checksums are
verified; a complete matching roster is required and conflicting versions fail.
The adapter copies sessions in memory and never rewrites the FastF1 cache or
historical library. Archived feeds may contain later corrections; they do not
prove original publication times. Unknown deleted-lap status can leave all Q
timings unavailable; rank remains usable with a labelled base-lap reference
estimate and missing timing predictors.

Fit an inactive artifact for the actual target year/round/event:

```powershell
.\.venv\Scripts\python.exe -m scripts.train_qualifying_pace --target-year YEAR --target-round ROUND --event "EVENT" --qualifying-results "PATH_TO_SAVED_Q_CSV_OR_LIBRARY" --output "NEW_ARTIFACT_PATH.json"
```

For a local post-Q run, set `model.pace_blend` to
`qualifying_partial_pooling_v1`, `model.qualifying_pace_model_path` to that
artifact, and optionally `model.qualifying_classifications_path` to the saved
Q source. Target identity, training cutoff and source hashes are verified.
Matched-stint and historical-calibration combinations are rejected. The artifact
is copied into the new run's output for reproducibility.

## Explicit pit-stop scenarios

Set `model.race_engine` to `pit_scenarios_v1`. The first experiment is a
**free-air dry scenario model**, not an overtaking/traffic engine. It calculates
compound offsets and linear age costs lap by lap, charges pit losses on the
specified inlaps, and accumulates pace gaps over the full distance. It replaces
aggregate long-run, degradation and strategy penalties/noise; the generic
28-second pit/race allowance is removed before explicit stint costs are added.
Completed-distance classification charges only stint costs and stops reached
before retirement. The existing aggregate red-flag compression remains a
heuristic, not chronological interruption modelling.

Without `model.pit_scenarios_path`, two explicitly assumed scenarios receive
equal weights for each driver: M-H at 45% distance, and M-M-H at 30%/65% distance.
Pit loss is an assumed 22 seconds. Compound `(offset seconds, wear seconds/lap)`
is S `(-0.35, 0.08)`, M `(0, 0.05)`, H `(0.35, 0.03)`. These are predeclared
sensitivity assumptions, not measured circuit parameters or inventory checks.

An optional JSON list supplies `Driver`, unique `name`, `weight`, `pit_laps`,
`compounds`, and positive `pit_loss_seconds` per plan. Weights must sum to one
per driver and the roster must match exactly. Raw results include the selected
scenario, planned stops and stint/pit cost; distance classification also reports
completed stops. Traffic, undercuts through rejoin position, safety-car discounts,
pit stacking, fuel effects and dynamic tyre choices remain future work.

## Shared-clock car agents

`model.race_engine = "agent_laps_v1"` enables the local-only candidate described
in [agent-layer.md](agent-layer.md). It replaces aggregate pace/strategy/grid
penalties with fuel/tyre state, physical traffic, explicit pit delays, passing
and lapping. Its assumptions and dry-race limitations are explicit; all live
defaults and promotion gates remain unchanged.

## Retirement survival, separately

Set `model.retirement_model` to `survival_dnf_v1`. Ten distance intervals estimate
mechanical, incident and unspecified retirement hazards from prior races.
Finishers remain in the risk set through race distance; unknown/DNS/disqualified
outcomes are excluded. Team and driver estimates shrink to a population prior.
Occurrence and conditional distance derive from the same survival distribution;
the existing completed-lap ordering/classification is reused. Weather still
applies the existing DNF multiplier. Shared incidents, team-correlated failures
and changing weather hazards are not modelled.

## Offline comparisons and acceptance

Run `scripts.benchmark_feature_ablations` with Q-only variants `legacy`,
`qualifying_partial_pooling_v1`, `pit_scenarios_v1`, and `survival_dnf_v1`, an
explicit Q archive when needed, and every previous inspection ledger. Compare
two- and five-race histories with seeds 42/123/777. Common complete episodes,
source/input hashes, skips, grid/recent-form baselines and calibration bins are
saved. No-coverage runs now retain a rejection report. Earlier timing-derived
grid comparisons and new archive-backed comparisons have different inputs and
must not be mixed.

Tests establish cutoff safety, source/packet checks, configuration wiring,
conditional distance semantics and exact default compatibility; they do not
establish predictive improvement. Promotion still needs at least six development
and six fresh races per requested stage, at least 5% lower combined loss, no
outcome Brier regression, and review against the qualifying-order baseline.
The new candidates are available for manual local experiments, not yet new
automatic prospective trial arms. Existing prospective trials retain their own
source-pinned suites. Full traffic simulation, Sobol sampling and reinforcement
learning were not added in this increment.
