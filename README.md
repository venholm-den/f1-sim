# F1 Simulation and Fantasy Model

End-to-end Formula 1 race simulation and fantasy projection tooling.

The project loads FastF1 session data, builds driver pace and reliability features, blends current weekend signals with recent race baselines and trained historical-model calibration, runs Monte Carlo race simulations, estimates tyre strategy risk, calculates fantasy scoring, and exposes the workflow through both a CLI and a portable local pywebview app.

There is no Power BI custom visual implementation in this repository.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py --year 2026 --event latest --session Q --n-sims 5000 --no-discord
```

For the portable desktop app:

```powershell
python -m portable_app.web_main
```

To build the Windows portable app:

```powershell
pip install -r requirements-dev.txt
.\scripts\build_portable_app.ps1
```

The executable is written to:

```text
dist\F1RaceSimulatorPortable\F1RaceSimulatorPortable.exe
```

## Documentation

- [Setup](docs/setup.md)
- [Development and run commands](docs/development-and-run-commands.md)
- [Run the portable app](docs/portable-app.md)
- [Data fields and inputs](docs/data-fields-and-inputs.md)
- [Parameter reference](docs/parameter-reference.md)
- [Outputs](docs/outputs.md)
- [Data sources](docs/data-sources.md)
- [Model design](docs/model-design.md)
- [Data-source roadmap](docs/data-source-roadmap.md)
- [Output hygiene](docs/output-hygiene.md)
- [Backtest Discord output](docs/backtest-discord-output.md)

## Main Workflow

`main.py` runs the core pipeline:

1. Load the target event/session, or select the latest useful weekend session.
2. Export available weekend lap details.
3. Build current-session driver features and recent race baselines.
4. Add grid, weather, race-control, team reliability, and performance-profile signals.
5. Apply trained historical finish/DNF calibration when model artifacts are available.
6. Run Monte Carlo race simulations.
7. Calculate fantasy points and value metrics when prices are available.
8. Predict tyre strategies and optionally adjust them with same-event historical patterns.
9. Save snapshots for backtesting and generate report outputs.

## Active App Direction

The active desktop UI is the local web app wrapped with pywebview:

- Entry point: `portable_app/web_main.py`
- Python bridge/API: `portable_app/web_backend.py`
- Web assets: `portable_app/web/`
- Shared services: `src/app_services/`

Older Tkinter/PySide GUI prototypes have been removed so the repository has one clear portable-app path.

## Generated Local Artifacts

These are intentionally ignored by Git:

- `outputs/`
- `build/`
- `dist/`
- `data/cache/`
- `data/historical_model/`
- `data/models/`

Recreate historical model artifacts with:

```powershell
python scripts/build_historical_dataset.py --start-year 2022 --end-year 2026 --sessions Q R
python scripts/train_historical_model.py --historical-dir data\historical_model --model-dir data\models
```

## Tests

```powershell
python -m pytest
```

## Known Limitations

- Tyre inventory is estimated from lap/stint data, not official FIA/Pirelli barcode tracking.
- Weather, race-control, reliability, and tyre modifiers are modelled conservatively from available data and heuristics.
- Historical calibration depends on locally generated `data/models/` artifacts.
- Fantasy value output requires valid prices in `data/fantasy_prices.csv`.
