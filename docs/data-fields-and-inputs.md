# Data Fields and Inputs

## Runtime FastF1 Inputs

Pulled at runtime:

- Event schedule.
- Session laps: `session.laps`.
- Session weather: `session.weather_data`.
- Session classification/results: `session.results` when available.
- Lap telemetry for track layout rendering when available.

## Local Input Files

### `data\fantasy_prices.csv`

Used for fantasy value metrics.

Expected fields:

- `Driver`
- `Team`
- `fantasy_price`

If missing, the pipeline creates a template and skips value metrics until prices are filled.

### `data\track_profiles.csv`

Used for circuit assumptions, forecast fallback, and simulation modifiers.

Common fields:

- `Event`
- `OvertakingDifficulty`
- `SafetyCarChance`
- `RedFlagBaseChance`
- `Latitude`
- `Longitude`
- `Notes`

### `data\team_power_units.csv`

Used for inferred team and power-unit reliability.

Common fields:

- `Year`
- `Team`
- `PowerUnitSupplier`

### `data\fia_documents\fia_document_index.csv`

Optional local index for official FIA context.

Common fields:

- `year`
- `event`
- `document_type`
- `driver`
- `team`
- `position`
- `penalty`
- `notes`
- `source_url`

Official starting grid rows override qualifying/model grid assumptions when available. Penalty rows are carried into grid outputs as FIA penalty notes.

## Generated Historical Model Inputs

Created by `scripts/build_historical_dataset.py`:

- `data\historical_model\fastf1_laps.csv`
- `data\historical_model\fastf1_race_results.csv`
- `data\historical_model\fastf1_actual_strategy.csv`
- `data\historical_model\fastf1_weather_summary.csv`
- `data\historical_model\fastf1_race_control_summary.csv`
- `data\historical_model\manifest.csv`

Created by `scripts/train_historical_model.py`:

- `data\models\historical_feature_table.csv`
- `data\models\historical_finish_model.joblib`
- `data\models\historical_dnf_model.joblib`
- `data\models\historical_model_metrics.json`

These folders are local generated artifacts and are ignored by Git.

## Key Model Feature Outputs

`outputs\driver_model_features.csv` contains the driver-level feature frame used by simulation. Important fields include:

- `Driver`
- `Team`
- `grid_position`
- `grid_source`
- `current_signal_quality`
- `effective_current_weight`
- `model_pace`
- `model_uncertainty`
- `quali_pace_score`
- `race_pace_score`
- `long_run_pace_score`
- `tyre_deg_score`
- `strategy_score`
- `reliability_score`
- `engine_reliability_score`
- `historical_model_available`
- `historical_predicted_finish`
- `historical_dnf_probability`
- `projected_lap_time`

## Environment Inputs

- `F1_SIM_YEAR`
- `F1_SIM_EVENT`
- `F1_SIM_SESSION`
- `F1_SIM_N_SIMS`
- `F1_SIM_RANDOM_SEED`
- `POST_TO_DISCORD`
- `DISCORD_WEBHOOK_URL`
