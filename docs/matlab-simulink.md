# MATLAB and Simulink validation

The MATLAB integration is a lap-by-lap strategy-validation layer around the
Python model. Python remains responsible for FastF1 collection, feature
engineering, calibration, and Monte Carlo simulation. Simulink consumes a
small versioned CSV contract so its dynamics can be tested without duplicating
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

When the strategy file does not contain explicit pit laps, the exporter places
the predicted number of stops evenly through the race. That is a transparent
baseline, not a claim that those are optimal pit windows.

## Rebuild the model

The `.slx` file is generated deterministically from MATLAB code:

```powershell
matlab -batch "addpath('matlab'); build_lap_dynamics_model"
```

Edit `matlab/build_lap_dynamics_model.m` rather than manually changing the
generated model so reviews can see the model topology as text.

## Run MATLAB tests

```powershell
matlab -batch "addpath('matlab'); results=runtests('matlab/tests'); assertSuccess(results)"
```

The test verifies that a pit stop adds the configured loss, resets tyre age on
the following lap, and leaves cumulative time equal to the sum of lap times.

## Calibration boundary

The initial fuel penalty, fuel gain per lap, pit loss, and maximum accepted tyre
degradation are exporter parameters. Defaults are deliberately conservative and
must be calibrated by circuit before the Simulink ranking is used as a model
feature. Values above the degradation cap remain visible in
`raw_tyre_degradation_seconds_per_lap` and are marked by
`degradation_was_capped`.
