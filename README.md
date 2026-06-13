# F1 Simulation and Fantasy Model

## Project overview

This repository runs an end-to-end Formula 1 simulation pipeline using FastF1 session data.
It builds driver pace features, blends current-session and recent race baselines, simulates race outcomes, computes fantasy scoring, predicts tyre strategy risk, and generates report images and CSV outputs.

The project is Python-based.
There is no Power BI custom visual implementation in this repository (no `pbiviz.json`, `capabilities.json`, or `src/visual.ts`).

## What the model does

Main workflow in `main.py`:

1. Load the latest usable session for the target year (prefers `Q`, then `SQ`, `S`, `FP3`, `FP2`, `FP1`).
2. Export weekend lap details across available sessions.
3. Infer estimated tyre set usage from lap/stint behavior.
4. Load track profile assumptions (`data/track_profiles.csv`).
5. Build weather modifiers from session weather data.
6. Build current-session driver features and baseline race features.
7. Blend features into model features and add grid position logic.
8. Add separated performance profile columns for quali, race, strategy, reliability, and projected lap-time signals.
9. Run Monte Carlo race simulations.
10. Compute fantasy scoring and optional value metrics (`xPPM`) if prices are provided.
11. Predict tyre strategies and optionally adjust them with historical same-event race baselines.
12. Save prediction snapshots for later backtesting.
13. Generate report charts, simulated race-time visualization, and commentary.
14. Optionally post a report bundle to Discord.

## Data fields and inputs

### FastF1 inputs

Pulled at runtime via FastF1:

- Session laps (`session.laps`)
- Session weather (`session.weather_data`)
- Session classification/results (`session.results` when available)
- Event schedule

### Local input files

- `data/fantasy_prices.csv`
	- Required columns for value calculations: `Driver`, `Price`
	- If missing, `main.py` creates a template file and value chart/`xPPM` is skipped until prices are filled.
- `data/track_profiles.csv`
	- Created automatically if missing.
	- Used fields: `Event`, `OvertakingDifficulty`, `SafetyCarChance`, `RedFlagBaseChance`, `Notes`
- `.env`
	- `POST_TO_DISCORD=true` enables Discord posting.
	- `DISCORD_WEBHOOK_URL=...` required when posting is enabled.

## Setup

### 1) Create and activate a virtual environment (recommended)

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2) Install dependencies

```powershell
pip install -r requirements.txt
```

### 3) Optional: scaffold missing folders/files

```powershell
python setup_project.py
```

## Development and run commands

### Run the full simulation pipeline

```powershell
python main.py
```

Runtime parameters are currently edited as constants in `main.py`:

- `YEAR`
- `TARGET_EVENT` (`"latest"` loads the latest usable predictor session)
- `TARGET_SESSION`
- `N_BASELINE_RACES`
- `N_SIMS`
- `SAVE_RAW_RESULTS`
- `HISTORICAL_STRATEGY_LOOKBACK_YEARS`

### Generate report card artifacts from existing outputs

```powershell
python test_report_card.py
```

### Inspect one driver in debug output

```powershell
python explain_driver.py
```

`explain_driver.py` uses the hardcoded `DRIVER` constant and expects existing `outputs/simulation_summary.csv` and `outputs/driver_model_features.csv` files.

### Backtest latest saved prediction after a race is complete

```powershell
python -m src.backtest
```

By default this reads `outputs/history/latest_prediction_snapshot.csv` and writes comparison artifacts to `outputs/backtest`.

## Build/package commands

This repository currently has no npm/pbiviz build or packaging workflow.
There is no `package.json`, `pbiviz.json`, or Power BI visual packaging step in the current codebase.

## Power BI data roles, field wells, and tooltips

No Power BI custom visual artifacts are present in the current repository.
That means there are currently no `capabilities.json` data roles, field wells, formatting cards, selection interactions, or tooltip definitions to document.

## Outputs

Primary generated files (non-exhaustive):

- Core model outputs
	- `outputs/current_session_features.csv`
	- `outputs/baseline_race_features.csv`
	- `outputs/driver_model_features.csv`
	- `outputs/simulation_summary.csv`
	- `outputs/position_matrix.csv`
	- `outputs/weather_summary.csv`
	- `outputs/raw_simulation_results.csv` (when `SAVE_RAW_RESULTS=True`)
	- `outputs/raw_fantasy_results.csv` (when `SAVE_RAW_RESULTS=True`)
- Lap detail exports
	- `outputs/lap_details/weekend_lap_details.csv`
	- `outputs/lap_details/practice_lap_summary.csv`
	- `outputs/lap_details/practice_long_run_summary.csv`
	- `outputs/lap_details/quali_lap_summary.csv`
	- `outputs/lap_details/quali_results_segments.csv`
- Tyre and strategy outputs
	- `outputs/tyres/tyre_set_ledger_estimated.csv`
	- `outputs/tyres/tyre_inventory_estimated.csv`
	- `outputs/strategy/predicted_tyre_strategy.csv`
	- `outputs/strategy/predicted_tyre_strategy_history_adjusted.csv`
	- `outputs/strategy/predicted_tyre_strategy.png`
- Historical strategy baseline outputs
	- `outputs/history/historical_strategy_driver_runs.csv`
	- `outputs/history/historical_strategy_summary.csv`
	- `outputs/history/historical_strategy_baseline.csv`
- Report assets
	- `outputs/report/race_dashboard.png`
	- `outputs/report/tyre_strategy_timeline.png`
	- `outputs/report/fantasy_risk_reward.png`
	- `outputs/report/simulated_race_times.png`
	- `outputs/report/model_commentary.txt`
	- `outputs/probabilities.png`
	- `outputs/detailed_report.png`
	- `outputs/fantasy_expected_points.png`
	- `outputs/fantasy_value.png` (only when prices are available)
- Backtest outputs
	- `outputs/history/*prediction_snapshot*.csv`
	- `outputs/history/latest_prediction_snapshot.csv`
	- `outputs/history/*prediction_snapshot*.config.json`
	- `outputs/backtest/*_actual_results.csv`
	- `outputs/backtest/*_comparison.csv`
	- `outputs/backtest/*_metrics.csv`
	- `outputs/backtest/*_recommendations.txt`

## Visual behavior and interactions

Report/plot behavior currently implemented:

- Team-colored bars and dark-theme chart/report styling across chart modules.
- Simulation summary + strategy risk are rendered into report-card images.
- Historical strategy adjustment can overwrite default tyre strategy output when same-event history indicates likely higher stop counts.
- Discord posting sends:
	- One long summary message (auto-split to respect Discord length limits)
	- Then report files as attachments.

There is no interactive UI/field-well behavior in this repository; outputs are static images and CSV files.

## Formatting options

No user-facing formatting pane exists in the current implementation.
Formatting is controlled in code (matplotlib styles, table labels, color maps, output paths).

## Known limitations

- Tyre inventory is estimated from lap data and tyre-life heuristics, not official FIA/Pirelli barcode set tracking.
- Historical strategy adjustment depends on event matching and available historical race data quality.
- If current session is practice, grid is estimated and uncertainty is intentionally increased.
- Rainfall and weather modifiers are conservative heuristics, not a full meteorological or circuit-specific calibration model.
- Fantasy value (`xPPM`) requires valid prices in `data/fantasy_prices.csv`.

## Troubleshooting

- `DISCORD_WEBHOOK_URL is missing. Add it to your .env file.`
	- Set `DISCORD_WEBHOOK_URL` in `.env`, or keep `POST_TO_DISCORD` disabled.
- `Snapshot not found: outputs/history/latest_prediction_snapshot.csv`
	- Run `python main.py` first to create a snapshot, then run backtest.
- `No laps found for ...`
	- FastF1 may not have that session yet, or the event/session identifier is unavailable.
- Strategy files are missing
	- Check that lap detail and tyre inventory outputs were created; strategy generation is skipped when upstream data is empty.
- Fantasy value chart is skipped
	- Fill numeric `Price` values in `data/fantasy_prices.csv`.

## Documentation guard

`scripts/check-docs-updated.ps1` is a pre-commit helper that warns when staged code/config files changed but `README.md` was not staged.
It prompts for explicit override (`y`) before allowing the commit to continue.

## Recent implementation changes

Current repository behavior includes:

- Weekend lap detail export and lap-summary outputs.
- Tyre set usage inference and estimated inventory outputs.
- Historical same-event strategy baseline adjustment.
- Structured report card image generation and textual model commentary output.
- Prediction snapshot saving and post-race backtesting utilities.
- Optional Discord report bundle posting controlled via `.env`.
