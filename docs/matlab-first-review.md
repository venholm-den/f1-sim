# First MATLAB/Simulink review — 7 September 2026

## Existing state

Reviewed commit `c20a8e8` and the local output snapshot. Python already has Monte
Carlo race outputs, strategy predictions and backtests. Simulink had one
five-lap regression case and one case per driver. It lacked scenario sensitivity
runs and rejected too few malformed inputs. Historical training artifacts under
`data/models` and `data/historical_model` were absent at review time.

The saved Hungarian Grand Prix backtest reports finish MAE 2.8578, finish
Spearman 0.8283 and top-10 overlap 0.9, with ANT predicted to win and NOR recorded
as actual winner. These are existing local backtest results, not a newly
verified external event record. The source snapshot is labelled qualifying,
2026 Hungarian Grand Prix; no new event data was downloaded for this review.

## Work completed

- Ran 242 Simulink cases: 22 drivers across 11 independently varied scenarios.
- Verified all 16,940 laps against an independent Python calculation, with
  maximum absolute error 5.46e-12 and tolerance 1e-8.
- Ran the MATLAB test suite: two test methods covering six simulation cases
  plus rejection checks for malformed schedules and nonfinite input.
- Ran the complete Python suite: 93 passed, two existing `utcnow` deprecation warnings.
- Fixed silent pit-schedule truncation, zero-cost stops being counted as zero,
  nonfinite parameter acceptance and short-race pit scheduling. Driver IDs are
  validated and cases must share a race distance.
- Preserved the observed degradation slope before upstream score clipping;
  recorded the source and flagged negative slopes. Three drivers in this
  snapshot have slopes floored at zero; none hit the upper cap.
- Added case/scenario identity, per-scenario ranking, repeatable exports and
  reference verification. Rebuilding now refuses to discard an unsaved model.

## Findings

| Change from baseline | Median time change (s) | Range across drivers (s) |
| --- | ---: | ---: |
| Pit windows 5 laps earlier | +0.725 | 0 to +1.640 |
| Pit windows 5 laps later | +0.725 | 0 to +1.640 |
| Degradation reduced 25% | -5.876 | -19.517 to 0 |
| Degradation increased 25% | +5.876 | 0 to +19.517 |
| Pit loss reduced 5 seconds | -7.500 | -10 to -5 |
| Pit loss increased 5 seconds | +7.500 | +5 to +10 |

Within the tested one/two/three-stop alternatives, one stop is fastest for 20
drivers and two stops for two. Twelve drivers have an alternative more than a
second faster than their exported baseline. ANT's one-stop scenario gains exactly
22 seconds because its negative observed degradation slope is floored at zero:
another tyre change has no modelled wear benefit and simply adds pit cost.

This exposes a limitation rather than proving the existing strategy predictor
wrong. The Simulink model uses one constant degradation slope and identical new
tyres after every stop. It has no compound pace differences, tyre warm-up,
traffic, safety cars or allocation constraints. Equal-length stints are favoured
by construction, explaining the symmetric early/late window effects. These
results do not justify feeding the current Simulink rank into race predictions.

## Next implementation priorities

1. Fit fuel/intercept and compound-specific degradation jointly from clean
   historical stints; retain uncertainty and hold out complete events. Current
   projected lap pace is not a zero-fuel reference, so absolute times may
   double-count fuel and wear already present in the input.
2. Use observed circuit pit losses and compound/warm-up parameters, then compare
   feasible compound sequences and pit windows for the same driver.
3. Build the missing historical training artifacts and evaluate model changes
   across held-out events before changing production weights. One saved race
   cannot establish improved predictive accuracy.

Production forecast weights were not changed. Experiment inputs, results and
checksums live under `outputs/matlab/experiments`; generated outputs remain
ignored by Git. Re-run using [the experiment commands](matlab-simulink.md).
