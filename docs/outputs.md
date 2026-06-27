# Outputs

Generated files are written under `outputs\` by default.

## Core Model Outputs

- `outputs\current_session_features.csv`
- `outputs\baseline_race_features.csv`
- `outputs\driver_model_features.csv`
- `outputs\simulation_summary.csv`
- `outputs\prediction_reasoning.csv` - driver-level explanation of grid source, model inputs, estimated time-loss components, and race simulation probabilities.
- `outputs\position_matrix.csv`
- `outputs\weather_summary.csv`
- `outputs\debug\reliability_profile.csv`
- `outputs\raw_simulation_results.csv` when raw output saving is enabled.
- `outputs\raw_fantasy_results.csv` when raw output saving is enabled.

## Lap Detail Outputs

- `outputs\lap_details\weekend_lap_details.csv`
- `outputs\lap_details\practice_lap_summary.csv`
- `outputs\lap_details\practice_long_run_summary.csv`
- `outputs\lap_details\quali_lap_summary.csv`
- `outputs\lap_details\quali_results_segments.csv`

## Tyre and Strategy Outputs

- `outputs\tyres\tyre_set_ledger_estimated.csv`
- `outputs\tyres\tyre_inventory_estimated.csv`
- `outputs\strategy\predicted_tyre_strategy.csv`
- `outputs\strategy\predicted_tyre_strategy_history_adjusted.csv`
- `outputs\strategy\predicted_tyre_strategy.png`

## Historical Strategy Outputs

- `outputs\history\historical_strategy_driver_runs.csv`
- `outputs\history\historical_strategy_summary.csv`
- `outputs\history\historical_strategy_baseline.csv`
- `outputs\history\latest_prediction_snapshot.csv`
- `outputs\history\*prediction_snapshot*.csv`
- `outputs\history\*prediction_snapshot*.config.json`

## Report Assets

- `outputs\report\race_dashboard.png`
- `outputs\report\tyre_strategy_timeline.png`
- `outputs\report\fantasy_risk_reward.png`
- `outputs\report\simulated_race_times.png`
- `outputs\report\model_commentary.txt`
- `outputs\probabilities.png`
- `outputs\detailed_report.png`
- `outputs\fantasy_expected_points.png`
- `outputs\fantasy_value.png` when prices are available.

## Backtest Outputs

- `outputs\backtest\*_actual_results.csv`
- `outputs\backtest\*_comparison.csv`
- `outputs\backtest\*_metrics.csv`
- `outputs\backtest\*_recommendations.txt`

## Calibration Outputs

- `outputs\calibration\calibration_report.json`
- `outputs\calibration\calibration_report.txt`

## Preview Images

Committed README/report preview images live under:

```text
assets\images\
```

These are documentation assets, not the runtime output location.
