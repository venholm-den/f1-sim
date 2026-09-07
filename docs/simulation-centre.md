# Simulation Centre

Double-click **Launch F1 Sim.cmd** in the repository folder. It opens the desktop
app using this project's `.venv`; no terminal commands are needed for normal use.
Keep one instance open at a time. This launcher uses the current source code;
an older executable under `dist` will not include these changes until rebuilt.

## Run and review

1. Check the saved-input event and date at the top. The initial data is the saved
   2026 Hungarian Grand Prix snapshot, not a newly downloaded race weekend.
2. Choose **Monte Carlo**, **Lap dynamics**, or **Scenario experiments**.
3. Adjust the settings and click **Start**. MATLAB startup can take a minute.
4. Review the live log, then select a driver/scenario in Results Explorer.
   The lap chart overlays the selected scenario and its baseline. With All drivers
   selected, the chart shows the first driver; the table includes everyone.
5. Reopen any run from history. Export the visible table into that run's `exports`
   subfolder, or open its results folder. Exports receive unique filenames.

Monte Carlo resamples saved features with neutral weather modifiers and offers
race count, random seed and overtaking difficulty. It does not regenerate the
full fantasy/strategy/report pipeline. Use **Race setup & full dashboard** for
fresh event inputs and that existing workflow; fetching data requires internet.

Lap dynamics runs all drivers through the Simulink model. Scenario experiments
run all 11 scenarios, or one change plus baseline: stop count, early/late pit
windows, degradation and pit-loss sensitivity. Zero-stop runs are diagnostics,
not claims of regulatory-valid dry-race strategies.

Each new run saves copied inputs, settings, a log and outputs in
`outputs/app_runs/<timestamp>_<id>/`. Earlier outputs remain unchanged.
**Cancel active run** stops the worker and its MATLAB child process on Windows.
Closing the desktop app also cancels its active Simulation Centre job. Partial
files can remain after cancellation; only completed runs should be used.

## Historical race data

Choose **Input source → Historical race / session**, pick a year, and click
**Load races**. Select a Grand Prix and session, then start any of the three
simulation modes. Seasons from 2018 onward are supported; only sessions scheduled
before today are offered. Archive availability can vary by event/session.

The first run downloads/caches FastF1 data and prepares inputs through the existing
pipeline, using two previous baseline races and one prior season of strategy
history. Preparation may take several minutes. Live weather forecasts, trained
historical calibration and Discord posting are disabled for these runs.

The selected year/event/session appears in run history. The run folder includes
`historical_config.json`, plus a `source` folder with prepared inputs and the full
pipeline's outputs. The main results explorer shows the selected simulation's
outputs, not the intermediate forecast used during preparation.
The pipeline's editable fantasy-price template is copied into `source/reference`
so a historical driver roster does not overwrite the current-season template.

After completion click **Use this run's historical inputs** to switch back to
saved-input mode with that archive selected. You can then run lap dynamics or
scenarios without repeating the preparation stage.

These are retrospective replays, **not leakage-free backtests**. The existing
preparation pipeline can use other/later sessions from the same weekend, and
reference tables/model assumptions remain current. Selecting Race (R) explicitly
uses race-session observations. Do not interpret replay results as a forecast
that would necessarily have been available at the selected session's date.

## Requirements and troubleshooting

- Existing Python environment: `.venv` with `requirements.txt` installed.
- Desktop window: pywebview and Microsoft Edge WebView2 runtime.
- MATLAB with a valid Simulink licence for both lap modes. MATLAB is found on PATH
  or under `C:\Program Files\MATLAB\R*\bin\matlab.exe`.
- If features are missing, use Race Setup first or select an output folder inside
  this project containing `driver_model_features.csv`. Experiments additionally
  need `strategy/predicted_tyre_strategy.csv`.
- On failure, expand **Live run log** for the actual Python/MATLAB error.

First-time Python setup (not needed on this configured machine):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Optional browser mode uses the same interface and backend, bound only to loopback:

```powershell
.\.venv\Scripts\python.exe -m portable_app.web_main --browser
```

In browser mode keep the terminal running; closing a browser tab does not stop
the server. Cancel the job in the app before stopping the server with Ctrl+C.

## Interpretation

Simulink results use exploratory fuel/tyre assumptions, not a calibrated vehicle
model. A verification badge means the saved lap outputs agree with the independent
Python arithmetic reference, not that race predictions match reality. Monte Carlo
probabilities depend on the selected feature snapshot and modelling assumptions.

## Verification of this implementation

Verified on the configured Windows workspace:

- 117 Python tests passed (two existing UTC deprecation warnings).
- App-launched Monte Carlo: 5,000 races, 22 driver results.
- App-launched Simulink lap dynamics: 22 driver cases completed.
- App-launched early-pit experiment: 44 cases / 3,080 laps independently verified.
- App cancellation of a MATLAB-backed job, persisted history after server restart,
  driver/scenario filtering, and browser rendering of the shared desktop UI.
- Filtered CSV export, the existing dashboard link, and clean native desktop
  startup through `Launch F1 Sim.cmd`. Native desktop visual interaction was not
  automated; UI interaction/rendering checks used the same assets in browser mode.
- Historical calendar loading for 2024 and a completed British Grand Prix Q replay
  (100 Monte Carlo races, 20 driver results). Historical inputs can be reused from
  the run history without repeating preparation.
- Simulink lap dynamics completed using those historical inputs (20 drivers).

The existing 242-case all-scenario results are also available in history. The
portable EXE packaging has not been rebuilt or retested in this change; use the
source launcher above.
