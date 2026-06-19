# Development and Run Commands

## Run the Main Pipeline

```powershell
python main.py
```

With common overrides:

```powershell
python main.py --year 2026 --event latest --session Q --n-sims 50000 --no-discord
```

Useful flags:

- `--config`
- `--year`
- `--event`
- `--session`
- `--n-sims`
- `--seed`
- `--baseline-races`
- `--default-overtaking-difficulty`
- `--strategy-lookback-years`
- `--post-to-discord`
- `--no-discord`

## Environment Overrides

- `F1_SIM_YEAR`
- `F1_SIM_EVENT`
- `F1_SIM_SESSION`
- `F1_SIM_N_SIMS`
- `F1_SIM_RANDOM_SEED`
- `POST_TO_DISCORD`

## Race Weekend Workflow

Use `--event latest` when you want the app to pick the best available predictor session. Priority is:

```text
Q -> SQ -> S -> FP3 -> FP2 -> FP1
```

Recommended rhythm:

| Weekend point | Command | Purpose |
| --- | --- | --- |
| Before FP1 | `python main.py --event latest --n-sims 1000 --no-discord` | Smoke-test dependencies, cache, config, prices, and outputs. |
| After FP1 | `python main.py --event latest --n-sims 5000 --no-discord` | Early low-confidence read. |
| After FP2 | `python main.py --event latest --n-sims 10000 --no-discord` | First useful long-run and fantasy direction. |
| After FP3 | `python main.py --event latest --n-sims 20000 --no-discord` | Final practice-based check before qualifying. |
| After Q or SQ | `python main.py --event latest --n-sims 50000 --no-discord` | Main pre-race prediction. |
| After official grid/penalties | Update `data\fia_documents\fia_document_index.csv`, then rerun the main prediction. | Apply FIA-confirmed grid and penalty context. |
| Final pre-race post | `python main.py --event latest --n-sims 50000 --post-to-discord` | Publish the report bundle. |
| After race | `python -m src.backtest` | Compare saved predictions to actual results. |
| After backtest | `python -m src.calibration` | Generate advisory tuning recommendations. |

For sprint weekends, run after `SQ` and again after `S` if sprint data should influence the race read.

## Backtest

```powershell
python -m src.backtest
```

By default this reads:

```text
outputs\history\latest_prediction_snapshot.csv
```

## Calibration Recommendations

```powershell
python -m src.calibration
```

With explicit metrics:

```powershell
python -m src.calibration --metrics "outputs/backtest/*_metrics.csv" --output-dir outputs/calibration
```

Calibration reports are advisory and do not edit code automatically.

## Historical Dataset and Model Training

```powershell
python scripts/build_historical_dataset.py --start-year 2022 --end-year 2026 --sessions Q R
python scripts/train_historical_model.py --historical-dir data\historical_model --model-dir data\models
```

For a quick smoke build:

```powershell
python scripts/build_historical_dataset.py --start-year 2026 --end-year 2026 --sessions R --max-events 1 --no-openf1
```

## Data-Source Roadmap Artifacts

```powershell
python scripts/build_data_source_roadmap.py
```

## Debug One Driver

```powershell
python explain_driver.py
```

`explain_driver.py` expects existing `outputs\simulation_summary.csv` and `outputs\driver_model_features.csv`.

## Tests

```powershell
python -m pytest
```

## Documentation Guard

```powershell
.\scripts\check-docs-updated.ps1
```

This helper warns when staged code/config files changed but README docs were not staged.
