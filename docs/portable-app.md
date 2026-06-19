# Run the Portable App

The active desktop app is a local web UI wrapped with pywebview and backed by Python services.

## Source Layout

```text
portable_app\web_main.py       # pywebview entry point
portable_app\web_backend.py    # Python API exposed to JavaScript
portable_app\web\index.html
portable_app\web\app.js
portable_app\web\styles.css
src\app_services\              # config, validation, run, output, and model-signal services
```

## Run From Source

```powershell
python -m portable_app.web_main
```

For pywebview debug mode:

```powershell
python -m portable_app.web_main --debug
```

## Build the Windows Portable App

Install dependencies:

```powershell
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Build:

```powershell
.\scripts\build_portable_app.ps1
```

Output:

```text
dist\F1RaceSimulatorPortable\F1RaceSimulatorPortable.exe
```

This is a folder-style PyInstaller onedir app. Keep the whole `dist\F1RaceSimulatorPortable\` folder together when sharing it.

## What the App Provides

- Race setup and run controls.
- Season and event dropdowns.
- Data-source status and CSV previews.
- Background simulation execution with run log.
- Dashboard charts for win, podium, DNF, and fantasy outcomes.
- Model Signals view including current-session signal quality, uncertainty, reliability, and historical calibration signals.
- Track map view with FastF1 track-position rendering when lap telemetry is available.
- Weather view with forecast/session weather summaries.
- Strategy and output tables.
- Race review view for completed-event outputs.

## Bundled Data

The build script bundles:

- `config\`
- `data\`
- `assets\`
- `portable_app\web\`
- FastF1 package data
- pywebview/pythonnet runtime data

If `data\models\historical_finish_model.joblib` and `data\models\historical_dnf_model.joblib` exist before building, they are included in the portable app bundle.

## Smart App Control

Windows may warn about unsigned locally built executables. For wider distribution, use a signed release build or distribute source instructions until signing is in place.
