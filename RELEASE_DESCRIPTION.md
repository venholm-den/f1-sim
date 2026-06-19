# v0.2.0-alpha.1 Pre-release

This alpha release introduces the new portable F1 Race Simulator desktop app and expands the model with historical calibration workflows. It is intended for early testing of the local app experience, packaging flow, and new model-signal surfaces before a stable release.

## Highlights

- New local desktop app built with `pywebview`, served from `portable_app/web_main.py`.
- Multi-view app UI for race setup, dashboard results, model signals, track map, weather, tyre strategy, race review, and data-source health.
- Windows portable app build script at `scripts/build_portable_app.ps1`.
- Historical data extraction and model training scripts for finish and DNF calibration.
- Optional historical calibration inputs wired into simulation runs.
- Real FastF1 track-layout rendering when telemetry is available.
- Event dropdowns, output refresh/open controls, run log streaming, and generated-output previews.
- Expanded documentation split into focused setup, run-command, output, data-source, parameter, and portable-app guides.
- Retired older GUI prototype files so the project has one active portable-app path.

## Getting Started

Run from source:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m portable_app.web_main
```

Build the Windows portable app:

```powershell
pip install -r requirements-dev.txt
.\scripts\build_portable_app.ps1
```

The build output is written to:

```text
dist\F1RaceSimulatorPortable\F1RaceSimulatorPortable.exe
```

Keep the full `dist\F1RaceSimulatorPortable\` folder together when sharing the built app.

## Historical Calibration

Historical model artifacts are optional local generated files. To rebuild them:

```powershell
python scripts/build_historical_dataset.py --start-year 2022 --end-year 2026 --sessions Q R
python scripts/train_historical_model.py --historical-dir data\historical_model --model-dir data\models
```

If `data\models\historical_finish_model.joblib` and `data\models\historical_dnf_model.joblib` exist before packaging, the portable build includes them.

## Alpha Notes

- This is a pre-release for testing and feedback.
- The executable is unsigned, so Windows may warn when launching local builds.
- FastF1 and weather data still require internet access on first data pulls.
- Generated caches, model artifacts, build outputs, and simulation outputs are local and intentionally not committed.
- Tyre inventory, weather modifiers, reliability, and historical calibration are modelled estimates rather than official FIA or Pirelli feeds.

## Since v0.1.0

This release adds the portable app rebuild, model-signal and data-health services, historical calibration pipeline, richer app documentation, updated image assets, and cleanup of the retired GUI prototype.
