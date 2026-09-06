# MATLAB and Simulink validation

The MATLAB integration is a lap-by-lap strategy-validation layer around the
Python model. Python remains responsible for FastF1 collection, feature
engineering, calibration, and Monte Carlo simulation. Simulink consumes a
small CSV contract so its dynamics can be tested without duplicating
the data pipeline.

## What the model adds

`matlab/models/f1_lap_dynamics_model.slx` evaluates each driver at one discrete
sample per lap. It exposes:

- fuel-load penalty falling through the race;
- tyre age and per-lap degradation;
- tyre-age reset after each predicted pit stop;
- pit-lane time loss;
- lap time and cumulative race time.

This is intentionally deterministic. Use it to inspect assumptions and compare
strategy shapes; keep probabilistic finishing outcomes in `src/simulate.py`.

## Run the integration

Prerequisites: MATLAB with Simulink, plus the project's Python dependencies.

```powershell
python scripts/export_simulink_inputs.py
matlab -batch "addpath('matlab'); run_lap_dynamics"
```

Or run both steps:

```powershell
.\scripts\run_matlab_validation.ps1
```

The default inputs are:

- `outputs/driver_model_features.csv`
- `outputs/strategy/predicted_tyre_strategy.csv`

The generated outputs are:

- `outputs/matlab/lap_dynamics_inputs.csv`
- `outputs/matlab/lap_dynamics_results.csv`
- `outputs/matlab/lap_dynamics_summary.csv`
- `outputs/matlab/lap_dynamics.png`

The exporter uses only the predicted number of stops from the strategy file and
always spaces stops evenly through the race. To test explicit windows, edit the
exported `pit_laps` column and keep `expected_stops` consistent. That is a transparent
baseline, not a claim that those are optimal pit windows.

## Rebuild the model

The model topology is reproducibly generated from MATLAB code (saved `.slx`
metadata can differ between builds):

```powershell
matlab -batch "addpath('matlab'); build_lap_dynamics_model"
```

Edit `matlab/build_lap_dynamics_model.m` rather than manually changing the
generated model so reviews can see the model topology as text.

## Run MATLAB tests

```powershell
matlab -batch "addpath('matlab'); results=runtests('matlab/tests'); assertSuccess(results)"
```

Tests exercise zero through three stops, initial used-tyre age, fuel reaching
zero, free pit stops, cumulative timing, and invalid schedules. Tests reuse the
committed model; they do not rewrite it on each run.

## Calibration boundary

The initial fuel penalty, fuel gain per lap, pit loss, and maximum accepted tyre
degradation are exporter parameters. Defaults are exploratory assumptions and
must be calibrated by circuit before the Simulink ranking is used as a model
feature. Values above the degradation cap remain visible in
`raw_tyre_degradation_seconds_per_lap` and are marked by
`degradation_was_capped`.

The exporter now prefers `deg_per_lap` to the already clipped `tyre_deg_score`,
records `degradation_source`, and flags negative estimates with
`degradation_was_floored`. A negative observed stint slope can reflect fuel burn
or other confounding effects; flooring it does not establish zero physical wear.
Likewise, `projected_lap_time` is not a measured zero-fuel, new-tyre baseline.
Adding explicit fuel and wear terms can double-count effects already in it.
Use within-driver scenario deltas for exploration until this intercept is fitted.

## Repeatable scenario experiments

From the repository root, with the Python environment active:

```powershell
python scripts/run_lap_experiments.py prepare
matlab -batch "addpath('matlab'); run_lap_dynamics('outputs/matlab/experiments/experiment_inputs.csv','outputs/matlab/experiments',false);"
python scripts/run_lap_experiments.py verify
```

This generates 11 scenarios per driver: baseline, zero/one/two/three stops,
pit windows shifted five laps early or late, degradation scaled by 0.75/1.25,
and pit loss reduced/increased by five seconds. Each factor changes separately;
interactions are not tested. Zero stops is a diagnostic only. No compound rules,
tyre allocation, warm-up, traffic, DNF, or weather are represented.

`case_id` identifies each driver/scenario pair in the exported results. Ranks
are calculated within each scenario, and the optional plot shows the first
scenario only. All cases must share one race distance. `pit_laps` must contain
unique increasing integer laps before the last race lap; a stop on lap p resets
age on lap p+1. Malformed schedules and nonfinite model parameters fail before
simulation, rather than being silently rounded or discarded.

The `experiments` output folder contains:

- `manifest.json`: exact source paths, checksums, scenarios and assumption limits.
- `experiment_inputs.csv`: all model cases, including editable pit schedules.
- `lap_dynamics_results.csv` and `lap_dynamics_summary.csv`: actual Simulink output.
- `verification.json`: counts, maximum error and exact input/output hashes.
- `scenario_comparison.csv`: driver-level time differences from baseline.
- `scenario_effects.csv` and `results.md`: aggregate scenario effects.

Verification checks every simulated lap, tyre age, fuel penalty, pit penalty and
cumulative time against an independent Python calculation, as well as stop
counts and final times. This validates implementation arithmetic, not predictive
accuracy. Input checksum changes require re-preparing and re-simulating.

See [first experiment review](matlab-first-review.md) for the initial findings.
