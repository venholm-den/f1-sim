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

## Track-rate safety cars

Set `model.safety_car_model` to `track_sc_v1` to add safety cars to the
aggregate engine (`src/safety_car.py`). The default `off` leaves the random
sequence and every output unchanged. Each simulated race deploys an SC with the
track profile's `SafetyCarChance` (TrackStatus 4 only; VSC is not modelled) at
a uniformly drawn race fraction. Gaps built before deployment shrink to 10% (the
queue residual), and the rest accrue after the restart, so the effect matches
the existing red-flag compression but depends on timing. Drivers take a stop
10 seconds cheaper with 60% probability when the SC falls between 15% and 80%
distance, and restarts add 1.5-second noise. These are stated assumptions, not
fitted values. It also applies to `pit_scenarios_v1`; the agent engine is
rejected because it has its own SC/VSC schedules. Raw results gain
`safety_car` and the summary gains `safety_car_chance`. Output is local-only.

`python -m scripts.benchmark_safety_car` replays a recent-baseline packet
(earlier races' pace plus the actual grid) with and without the candidate on
matched seeds. On the 23 October packet (rounds 4-16 of 2026, three-race history,
5,000 sims, seeds 42/123/777) it gave:

| Arm | Finish MAE | Win Brier | Podium Brier | Top-10 Brier |
| --- | ---: | ---: | ---: | ---: |
| Established engine | 3.664 | 0.0307 | 0.0730 | 0.1846 |
| `track_sc_v1` | 3.671 | 0.0303 | 0.0722 | 0.1791 |

Top-10 Brier improved in 11 of 13 races; finish MAE is flat. These races were
already inspected and the gain is below the 5% promotion gate, so this stays a
candidate. The profiles average a 42% SC chance against 54% observed in those
races, and six of the 13 used generic placeholders, so calibrating track SC rates
(`scripts.calibrate_circuits`) is the obvious next step.

## Shared team luck, sampled grids, grid penalties and sprints

Four more local-only candidates, each `off` by default. Each uses its own random
stream, so turning one off leaves the established engine's output unchanged.

| Setting | Value | What it does |
| --- | --- | --- |
| `model.shared_noise_model` | `team_noise_v1` | Adds one normal draw per team per race (3 s sd, times the weather uncertainty factor) to both drivers (`src/shared_noise.py`). Teammates move together, so a car that is quicker or slower than practice showed lifts or sinks both. |
| `model.grid_sampling_model` | `estimated_grid_v1` | When every grid slot is an estimate (before qualifying), draws a qualifying order per sim with 2-position noise instead of using one order in every race (`src/grid_penalties.py`). Grid loss, positions gained and Fantasy qualifying points then vary across sims. Actual and FIA grids are not sampled. |
| `model.grid_penalty_model` | `announced_v1` | Applies verified stewards' decisions for the race (grid drops, back of grid, pit-lane starts) to a grid that lacks them: the estimate or the qualifying classification. An FIA starting grid already includes them and is left alone. The qualifying order is kept as `qualifying_position`, and Fantasy qualifying points use it, so a penalised pole-sitter keeps them. Drops are applied together, not in order of infringement. |
| `model.sprint_model` | `sprint_v1` | On sprint weekends (FastF1 `EventFormat`, or SQ/S laps), simulates a sprint per sim (`src/sprint.py`): about 100 km, no stops, the forecast's grid, race noise and retirement risk scaled to the distance, points 8-1. Fantasy adds sprint points, the same per-place change rules and a DNF penalty (`FANTASY_SCORING['sprint_dnf_penalty']`, else the race value) as `avg_sprint_fantasy_points`. No sprint fastest-lap or overtake bonus. |

Shared noise and grid sampling apply to the aggregate engine only. The spreads are
stated assumptions, not fitted values.

`python -m scripts.benchmark_safety_car --arms established team_noise_v1
estimated_grid estimated_grid_v1` runs the same packet as above. The
`estimated_grid` arms swap the actual grid for a pace-ranked estimate, which is
what a pre-qualifying forecast sees, so compare `estimated_grid_v1` with
`estimated_grid`, not with the established engine. Same packet, sims and seeds:

| Arm | Finish MAE | Win Brier | Podium Brier | Top-10 Brier |
| --- | ---: | ---: | ---: | ---: |
| Established engine | 3.664 | 0.0307 | 0.0730 | 0.1846 |
| `team_noise_v1` | 3.666 | 0.0305 | 0.0730 | 0.1828 |
| Estimated grid, one order | 3.891 | 0.0382 | 0.0815 | 0.1986 |
| `estimated_grid_v1` | 3.893 | 0.0380 | 0.0814 | 0.1985 |

Team noise improved top-10 Brier in 10 of 13 races, with finish MAE flat. Grid
sampling is close to neutral on these scores; its main effect is realistic spread
in Fantasy qualifying points, which this packet does not score. Both gains are
below the 5% promotion gate on already inspected races, so they stay candidates.
Grid penalties and sprints cannot be scored from this packet.

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
