# Parameter Reference

The project uses JSON config, editable CSVs, and code-level constants. This page groups the main parameters by purpose.

## Run Selection and Simulation Volume

Defined in `config\default_run_config.json` under `run`.

| Parameter | Purpose |
| --- | --- |
| `year` | F1 season to load. |
| `event` | Event name, round number, or `latest`. |
| `session` | Preferred session code: `FP1`, `FP2`, `FP3`, `Q`, `SQ`, `S`, or `R`. |
| `n_sims` | Monte Carlo race count. |
| `random_seed` | Reproducibility seed. |
| `n_baseline_races` | Recent races used for pace and reliability baselines. |
| `default_overtaking_difficulty` | Fallback track-position difficulty. |
| `historical_strategy_lookback_years` | Same-event history window used by tyre strategy adjustment. |

## Output Toggles

Defined under `outputs`.

| Parameter | Purpose |
| --- | --- |
| `output_dir` | Root folder for generated files. |
| `save_prediction_snapshot` | Writes a snapshot for future backtesting. |
| `save_report_images` | Enables report image generation. |
| `save_raw_results` | Saves raw simulation/fantasy rows. |
| `post_to_discord` | Sends the report bundle when webhook settings exist. |

## Data Paths

Defined under `data`.

| Parameter | Purpose |
| --- | --- |
| `fantasy_prices_path` | Fantasy price input. |
| `track_profiles_path` | Circuit assumptions and coordinates. |
| `fia_document_index_path` | FIA grid, penalty, and classification context. |
| `team_power_units_path` | Team-to-power-unit mapping. |

## Model Switches

Defined under `model`.

| Parameter | Purpose |
| --- | --- |
| `model_version` | Label written into model outputs. |
| `use_fastf1_weather` | Keeps FastF1 weather enabled where supported. |
| `use_weather_forecast` | Allows Open-Meteo forecast fallback when session weather is missing. |
| `use_race_control_context` | Allows race-control signals to influence chaos/weather modifiers. |
| `use_track_red_flag_base_chance` | Uses track-specific red-flag baseline chance. |
| `use_historical_model_calibration` | Enables trained historical finish/DNF model calibration. |
| `historical_model_dir` | Folder containing historical sklearn artifacts. |
| `historical_finish_weight` | Blend weight for historical predicted finish into race pace score. |
| `historical_dnf_weight` | Blend weight for historical DNF probability into reliability score. |

## Editable Data Tables

| File | Main parameters |
| --- | --- |
| `data\track_profiles.csv` | `OvertakingDifficulty`, `SafetyCarChance`, `RedFlagBaseChance`, `Latitude`, `Longitude`. |
| `data\team_power_units.csv` | `Year`, `Team`, `PowerUnitSupplier`. |
| `data\fantasy_prices.csv` | Driver/team fantasy prices. |
| `data\fia_documents\fia_document_index.csv` | Official grid, penalty, classification, summons, and notes. |

## Session Weighting and Pace Blending

Defined mainly in `src\model.py`, `src\performance.py`, and `src\model_config.py`.

| Parameter/group | Purpose |
| --- | --- |
| `CURRENT_SESSION_WEIGHTS` | Current-session blend by session type. |
| `SESSION_WEIGHTS` | Splits current-session influence across quali, race, and strategy scores. |
| `baseline_weight = 1 / (1 + baseline_age * 0.45)` | Downweights older baseline races. |
| `current_signal_quality` | Scales current-session influence using clean laps, variance, and outlier checks. |
| Practice pace cap | Reduces overreaction to practice fuel, traffic, and run plans. |
| Qualifying pace cap | Keeps quali signals strong but bounded. |
| `model_uncertainty` | Built from baseline spread, baseline coverage, session type, and signal quality. |

## Weather and Race-Control Modifiers

Defined mainly in `src\weather.py` and `src\race_control.py`.

| Parameter/group | Purpose |
| --- | --- |
| `chaos_factor` | Increases race noise and incident risk. |
| `strategy_factor` | Increases strategy loss/noise. |
| `dnf_factor` | Scales simulated DNF probability. |
| `degradation_factor` | Scales tyre degradation loss and strategy assumptions. |
| `uncertainty_factor` | Scales race noise. |
| Rainfall flag | Adds chaos, strategy variance, DNF risk, and uncertainty. |
| Track temperature thresholds | Adjust tyre degradation and uncertainty. |
| Wind thresholds | Increase chaos and uncertainty for moderate/high wind. |
| Race-control context | Raises chaos, strategy, DNF, and uncertainty factors from incidents/messages. |

## Reliability and DNF Parameters

Defined mainly in `src\features.py`, `src\reliability.py`, `src\performance.py`, and `src\simulate.py`.

| Parameter/group | Purpose |
| --- | --- |
| Feature `dnf_prob` | Starts from lap-data quality. |
| `DEFAULT_MECHANICAL_DNF_RATE = 0.045` | Prior when recent result status data is sparse. |
| `DEFAULT_PRIOR_WEIGHT = 8.0` | Smoothing weight for team and power-unit rates. |
| Mechanical status keywords | Detect engine, gearbox, hydraulics, brakes, and power-unit DNFs. |
| Non-mechanical status keywords | Detect accidents, collisions, crashes, and similar statuses. |
| Reliability blend | Combines base `dnf_prob`, team mechanical rate, and power-unit mechanical rate. |
| `reliability_score` | Final DNF probability signal passed into simulation. |
| `effective_dnf_prob` | Simulation DNF probability after weather/race-control `dnf_factor`. |

## Race Simulation Engine

Defined in `src\model_config.py` under `SIMULATION_PARAMETERS`.

| Parameter | Purpose |
| --- | --- |
| `race_pace_seconds_multiplier` | Converts race pace score into time loss. |
| `long_run_penalty_multiplier` | Penalizes weak long-run pace. |
| `tyre_deg_multiplier` | Converts degradation score into race time loss. |
| `grid_loss_multiplier` | Converts grid position and overtaking difficulty into time loss. |
| `strategy_loss_multiplier` | Converts strategy score into time loss. |
| `race_noise_multiplier` | Driver/race stochastic pace noise. |
| `start_noise_seconds` | Start phase randomness. |
| `strategy_noise_seconds` | Strategy randomness. |
| `chaos_noise_seconds` | Incident/weather chaos randomness. |
| `red_flag_field_compression` | Compresses field spread under simulated red flags. |
| `red_flag_noise_seconds` | Adds noise after red-flag compression. |

## Fantasy Scoring

Defined in `src\model_config.py` under `FANTASY_SCORING`.

| Parameter/group | Purpose |
| --- | --- |
| `finish_points` | Points by race finish. |
| `quali_points` | Points by qualifying position. |
| `position_gain_points_per_place` | Reward for race positions gained. |
| `position_loss_points_per_place` | Penalty for positions lost. |
| `position_change_min` / `position_change_max` | Caps position-change scoring. |
| `fastest_lap_bonus` | Fastest lap fantasy bonus. |
| `dotd_bonus` | Driver of the day fantasy bonus. |
| `dnf_penalty` | Fantasy DNF penalty. |

## Tyre Strategy Parameters

Defined mainly in `src\tyres.py`, `src\strategy.py`, and `src\strategy_history.py`.

| Parameter/group | Purpose |
| --- | --- |
| Assumed dry tyre allocation | Starting hard/medium/soft sets by weekend format. |
| Tyre status classification | Estimates new, scrubbed, used, or unknown sets. |
| Inventory risk score | Combines shortage pressure, unknown stints, and confidence penalties. |
| Degradation fallback | Driver long-run, team long-run, field long-run, weather-adjusted default. |
| Candidate strategy scoring | Ranks dry plans and two-stop variants. |
| High degradation threshold | Pushes strategy selection toward two-stop candidates. |
| Overtaking difficulty thresholds | Reward track-position preservation or recovery strategies. |
| Old/unknown tyre penalty | Penalizes likely used or unknown dry sets. |
| Historical adjustment thresholds | Uses same-event history when sample size and signal strength are high enough. |

## Backtest and Calibration

Defined mainly in `src\model_config.py`, `src\backtest.py`, and `src\calibration.py`.

| Parameter/group | Purpose |
| --- | --- |
| `BACKTEST_METRIC_WEIGHTS` | Weights finish MAE, Brier scores, and fantasy MAE. |
| Backtest snapshots | Saved predictions later compared with actual results. |
| Calibration recommendations | Reads backtest metrics and suggests tuning changes. |
