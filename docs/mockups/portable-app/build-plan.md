# Portable App Build Plan

## Recommendation

Build the mockup as a new portable desktop app shell rather than stretching the current `app_gui.py`.

The existing Tkinter GUI is useful as a lightweight runner, but the mockups describe a richer dashboard with navigation, cards, validation panels, editable tables, charts, scenario tabs, and post-run results. That kind of interface will be cleaner if the app has a small UI layer on top of reusable simulator services.

Best path:

1. Keep `main.py` as the command-line pipeline.
2. Keep `app_gui.py` as the simple runner for now.
3. Add a new portable app package that calls shared services instead of duplicating simulation logic.

Recommended UI stack:

- **PySide6 / Qt** for the full mockup experience.
- Keep **PyInstaller onedir** packaging for Windows portability.
- Use the existing `matplotlib` image outputs initially, then add native embedded charts later.

PySide6 is heavier than Tkinter, but it fits this design better: sidebar navigation, cards, tables, tabs, progress views, file pickers, theme control, and richer state handling are all much easier.

## Target App Shape

The mockups map to these top-level sections:

1. **Race Setup**
   - Core run parameters.
   - Output toggles.
   - Track/weather preview.
   - Run readiness.
   - Run Simulation action.

2. **Data Sources**
   - Config/data file status.
   - Row counts.
   - Missing/stale warnings.
   - CSV preview.
   - Open folder / open editor / reload / validate all.

3. **Model Signals**
   - Current-session weight display.
   - Session weight controls.
   - Baseline decay.
   - Practice/quali caps.
   - Model uncertainty.
   - Input signal distribution.
   - Explainability notes.

4. **Weather & Reliability**
   - Weather source and forecast.
   - Race-control context.
   - Chaos/strategy/DNF/degradation/uncertainty factors.
   - Safety-car and red-flag risk.
   - Reliability table from `outputs/debug/reliability_profile.csv`.

5. **Tyre Strategy**
   - Predicted strategy table.
   - Candidate strategy scores.
   - Historical adjustment columns.
   - Tyre inventory risk.
   - Degradation source/confidence.

6. **Fantasy**
   - Fantasy scoring settings.
   - Price/value table.
   - xPPM and value tier outputs.

7. **Results**
   - Win/podium/top-10 probability.
   - Finish distribution.
   - Fantasy projections.
   - Strategy recommendations.
   - Export buttons.
   - Discord post action.

8. **Compare**
   - Later phase.
   - Run multiple scenarios side by side.
   - Dry/wet/safety-car/red-flag presets.

9. **Settings**
   - Data directory.
   - Output directory.
   - App settings.
   - Discord webhook status.
   - Reset defaults.

## Architecture

Add a small app service layer before building the full UI.

Suggested structure:

```text
src/app_services/
  __init__.py
  config_service.py
  data_health.py
  run_service.py
  output_index.py
  preview_readers.py
  scenario_service.py

portable_app/
  __init__.py
  main.py
  theme.py
  state.py
  widgets/
  screens/
    race_setup.py
    data_sources.py
    model_signals.py
    weather_reliability.py
    tyre_strategy.py
    fantasy.py
    results.py
    compare.py
    settings.py
```

The UI should not call random project internals directly. It should use service functions such as:

- `load_app_settings()`
- `save_app_settings()`
- `load_run_config()`
- `save_run_config()`
- `validate_data_sources()`
- `build_temp_run_config()`
- `run_simulation_async()`
- `list_output_files()`
- `load_results_summary()`
- `load_strategy_outputs()`
- `load_reliability_profile()`

## Local Settings

Add an app-local settings file that is separate from simulation config:

```text
app_settings.json
```

Example:

```json
{
  "data_dir": "data",
  "output_dir": "outputs",
  "last_config_path": "config/default_run_config.json",
  "theme": "dark",
  "auto_reload_data": true,
  "open_output_after_run": false
}
```

Keep secrets out of exported files. Discord webhook should stay in `.env` or another local-only secret store.

## Build Phases

### Phase 1 - Service Layer

Goal: make the simulator controllable by a GUI without duplicating logic.

Tasks:

- Extract config read/write helpers from `app_gui.py` into `src/app_services/config_service.py`.
- Add data health checks:
  - file exists
  - row count
  - required columns
  - modified time
  - stale/missing/valid status
- Add output index helpers for generated CSV/images.
- Add a run worker that can run the pipeline with a temp config and stream logs.
- Add tests for services.

Exit criteria:

- A test can create a temp run config.
- A service can validate `data/fantasy_prices.csv`, `data/track_profiles.csv`, `data/team_power_units.csv`, and the FIA index.
- A service can list generated output files after a run.

### Phase 2 - Portable App MVP

Goal: replace the current simple GUI with the first two mockup screens.

Build:

- PySide6 app shell.
- Left sidebar navigation.
- Race Setup screen.
- Data Sources screen.
- Run Simulation button.
- Log/progress drawer or panel.
- Open output folder action.

Keep the app functional before making it beautiful.

Exit criteria:

- User can configure a normal run.
- User can validate data files.
- User can run simulation.
- User can see run status and open outputs.

### Phase 3 - Results Viewer

Goal: make the app useful after a run.

Build:

- Results screen.
- Read `outputs/simulation_summary.csv`.
- Read `outputs/position_matrix.csv`.
- Show win/podium/top-10 tables.
- Show generated report images.
- Show strategy recommendations from `outputs/strategy/predicted_tyre_strategy_history_adjusted.csv` when available.
- Export/open actions.

Exit criteria:

- After a run, the Results screen populates without restarting the app.
- Missing output files show friendly messages.

### Phase 4 - Advanced Model Screens

Goal: expose the new parameters and debugging signals.

Build:

- Model Signals screen from model/config outputs.
- Weather & Reliability screen using weather summary, race-control context, and `outputs/debug/reliability_profile.csv`.
- Tyre Strategy screen with candidate scores and inventory risks.
- Fantasy screen with scoring and price/value outputs.

Exit criteria:

- User can inspect why a run behaved the way it did.
- User can identify stale data or weak-confidence assumptions.

### Phase 5 - Scenario Compare

Goal: support dry/wet/high-chaos/high-deg scenario runs.

Build:

- Scenario presets.
- Run queue.
- Scenario tabs.
- Side-by-side summary comparison.
- Difference table for driver probabilities and fantasy value.

Exit criteria:

- User can run at least two scenarios and compare results.

### Phase 6 - Packaging

Goal: make the app shareable as a local Windows portable app.

Build:

- PyInstaller `onedir` bundle.
- Include `config/`, `data/`, assets, and app package.
- Use writable folders outside bundled read-only assets.
- Add first-run copy of default config/data to user-writable app folder if needed.
- Add troubleshooting notes for SmartScreen/Smart App Control.

Exit criteria:

- Clean local build.
- App runs from `dist/`.
- User can choose output folder.
- App does not require admin permissions.

## Suggested First Implementation Branch

Create a branch like:

```powershell
git switch -c portable-app-service-layer origin/main
```

Start with the service layer, not the UI. That reduces risk and gives the future GUI a clean API.

## Why Not Build Everything Directly in the UI?

The simulator already has useful command-line and reporting logic. If the UI starts importing and mutating all of that directly, it will become fragile quickly.

A service layer lets the app stay stable while the model continues evolving.

## Near-Term MVP

The smallest useful app matching the mockups is:

1. Race Setup screen.
2. Data Sources screen.
3. Run log/progress.
4. Results screen that opens generated CSV/images.
5. PyInstaller build.

Everything else can land after the portable app is already usable.
