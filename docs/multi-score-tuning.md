# Multi-score settings tuning

`scripts.tune_multi_score` fits several simulation settings together instead
of sweeping one at a time. It follows the calibration protocol in the Pitwall
Monte Carlo paper ([arXiv 2607.06495](https://arxiv.org/pdf/2607.06495)):

- **Objective (higher is better):** Spearman rank correlation between simulated
  average finish and the classified result, minus 2 x the mean of the win,
  podium and top-10 Brier scores, minus 1 x the 10-bin expected calibration
  error (ECE). Rank correlation and Brier average races equally; ECE pools
  every driver-outcome probability, because one race has too few rows per bin.
- **Optimiser:** bounded differential evolution (SciPy). The initial
  population includes the live settings, so the current engine is always a
  candidate. Every candidate shares one simulation seed (common random
  numbers), so differences reflect settings rather than sampling noise.
- **Season-blocked split:** settings are fitted on whole earlier seasons and
  scored once on later held-out seasons. Every fit season must precede every
  held-out season. 2026 is refused because its races are reserved for
  prospective trials and earlier benchmarks.

## Tuned settings

| Setting | Live | Bounds |
| --- | ---: | --- |
| `race_pace_seconds_multiplier` | 0.20 | 0.05 to 0.60 |
| `grid_loss_multiplier` | 1.65 | 0 to 15 |
| `race_noise_multiplier` | 3.80 | 1 to 8 |
| `start_noise_seconds` | 1.15 | 0.25 to 4 |
| `strategy_loss_multiplier` | 2.50 | 0.5 to 6 |

Tuned values reach the engine only through the per-call
`simulate_races(..., parameter_overrides=...)` argument. Omitting it keeps
`SIMULATION_PARAMETERS`; the tool never edits config or live defaults.

## Run

```powershell
python -m scripts.tune_multi_score --cache-dir data/cache --fit-years 2022 2023 --holdout-years 2024 --sessions Q
```

Features are built once per race/stage with the same leakage-safe replay used
by the accuracy benchmark (`build_replay_inputs`), so a run costs roughly one
simulation call per fit race per candidate. Defaults are 500 simulations while
tuning and 2,000 simulations over seeds 42, 123 and 777 when scoring.

Pass earlier benchmark reports with `--inspected-reports`. Held-out races named
in them are scored but labelled previously inspected and excluded from the gate.

## Outputs

A new folder under `outputs/multi_score_tuning/` (an existing folder is
refused) with `report.json`, `optimizer_history.csv`, `summary.csv`,
`predictions.csv`, `calibration_bins.csv` (reliability-diagram rows),
`brier_decomposition.csv` (reliability, resolution and uncertainty per
outcome), `grid_order_baseline.csv` and `identifiability_profile.csv`.

The identifiability profile varies one setting across its bounds with the
others held at the fit. A setting whose objective moves less than 0.005 is
reported as weakly identified: the fit seasons cannot pin it down, so its tuned
value should not be trusted on its own. This is a cheap stand-in for the
paper's CMA-ES identifiability check.

## Promotion gate

The gate passes only with at least six unseen held-out races, at least a 0.01
held-out objective gain over the live settings, and no held-out regression in
Brier, ECE or rank correlation. Passing is evidence for review, not
deployment; any live change still goes through the normal promotion review.
