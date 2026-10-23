# Single degradation candidate (`single_degradation_v1`)

The legacy engine counts practice tyre degradation (`deg_per_lap`, clipped to
`tyre_deg_score`) four times:

| Path | Where | Effect of +0.05 s/lap over 57 laps |
| --- | --- | ---: |
| `degradation_loss` | `src/simulate.py`, `× laps × tyre_deg_multiplier (7.0)` | 20.0 s |
| `long_run_pace_score` | `src/performance.py`, `deg × 12`, then `× laps × 0.25` in `long_run_loss` | 8.6 s |
| `strategy_score` | `src/performance.py`, `deg × 2 to 4`, then `× 2.5` | 0.25 to 0.5 s |
| `degradation_noise` | `src/simulate.py`, sd `deg × laps × 1.4` | wider spread only |

A 0.5 s/lap race-pace gap costs 5.7 s (`× laps × 0.20`). Practice degradation
slopes also include fuel burn and mixed programmes, so the noisiest input has
the largest weight.

## The candidate

`single_degradation_v1` counts degradation once:

- `single_degradation()` in `src/accuracy_candidates.py` removes the wear terms
  from `long_run_pace_score` and `strategy_score`. Pace, uncertainty and the
  rest of the strategy baseline are unchanged.
- `simulate_races(single_degradation_multiplier=2.0)` uses that weight for
  `degradation_loss` and gives every driver the field-median degradation
  noise, so overall spread is kept but a high-wear estimate no longer widens
  one driver's outcomes.

The weight 2.0 is predeclared, not fitted. A two-stint race costs roughly
14× the per-lap wear slope per lap; the engine scores pace at 0.20 of its
full-distance value, which gives about 2.8, rounded down for noisy practice
slopes. With it, a 0.05 s/lap wear gap costs 5.7 s, the same as a 0.5 s/lap
pace gap.

The default engine is unchanged: `single_degradation_multiplier=None` is
bit-for-bit the legacy result, and scheduled forecasts do not use the variant.

## Offline replay (23 October)

`python -m scripts.benchmark_degradation_offline` replays PRE forecasts from
`data/recent_baselines/singapore-20261005-v4-venues` (2026 rounds 1 to 16,
race sessions only), 5,000 simulations, seeds 42/123/777. Rounds 3, 12 and 15
are skipped for incomplete driver coverage. These races have been inspected,
so the numbers are diagnostic, not fresh validation.

Two prior races as baseline (development rounds 4 to 9, holdout 10 to 16):

| Arm | Dev MAE | Dev loss | Holdout MAE | Holdout loss | Holdout podium Brier | Holdout win Brier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Legacy | 4.265 | 4.479 | 3.838 | 3.993 | 0.0745 | 0.0351 |
| Single, weight 2.0 | 4.102 | 4.311 | 3.331 | 3.468 | 0.0727 | 0.0342 |
| Grid order | 4.439 | 4.727 | 3.273 | 3.491 | 0.1091 | 0.0545 |

Five prior races as baseline (`--n-baseline-races 5`, development 6 to 10,
holdout 11 to 16): legacy loss 4.107 / 3.499, single 2.0 loss 3.999 / 3.182.

The sensitivity sweep (`--multipliers 0 1 2 3 5 7`) has its best development
loss at 3.0 (two-race baseline) and 5.0 (five-race baseline), with 2.0 within
1% of each. Even at 7.0, removing the duplicate paths alone beats legacy. No
probability Brier score regresses at 2.0 in either split.

Loss is finish MAE + top-10 Brier, as in the other benchmarks. Before
promotion, run the cached FastF1 comparison including FP2 and Q:

```
python -m scripts.benchmark_feature_ablations --prior-report <report> \
  --variants legacy single_degradation_v1
```

`src/prediction_reasoning.py` still explains forecasts with the legacy
weights; update it alongside any promotion.
