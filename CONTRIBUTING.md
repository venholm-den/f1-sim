# Contributing

Thanks for helping improve `f1-sim`. This project combines Formula 1 data collection, simulation modelling, generated report outputs, and a portable local app, so small focused changes are easiest to review.

## Development Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Run the simulation:

```powershell
python main.py --year 2026 --event latest --session Q --n-sims 5000 --no-discord
```

Run the portable app:

```powershell
python -m portable_app.web_main
```

Build the Windows portable app:

```powershell
.\scripts\build_portable_app.ps1
```

## Tests

Before opening a pull request, run:

```powershell
pytest
```

For documentation-only changes, say that tests were not run because the change is docs-only.

## Documentation

Update docs when behavior, commands, config, outputs, data files, or app workflows change. Useful starting points:

- `README.md`
- `docs/setup.md`
- `docs/development-and-run-commands.md`
- `docs/portable-app.md`
- `docs/parameter-reference.md`
- `docs/outputs.md`
- `docs/data-sources.md`

The helper script below warns when staged code/config changes do not include README updates:

```powershell
.\scripts\check-docs-updated.ps1
```

## Pull Request Guidelines

- Keep the change focused.
- Explain the problem and the chosen fix.
- Include screenshots or generated output examples for UI/report changes where useful.
- Add or update tests for behaviour changes.
- Avoid committing generated local artifacts such as `outputs/`, `build/`, `dist/`, `data/cache/`, `data/historical_model/`, or `data/models/`.
- Do not commit secrets, `.env` files, API keys, Discord webhooks, or personal data exports.

## Data and Model Changes

When changing model logic, be explicit about the expected effect on outputs such as finish probabilities, DNF risk, fantasy points, tyre strategy, or calibration. If the change depends on generated model artifacts, document how to rebuild them:

```powershell
python scripts/build_historical_dataset.py --start-year 2022 --end-year 2026 --sessions Q R
python scripts/train_historical_model.py --historical-dir data\historical_model --model-dir data\models
```
