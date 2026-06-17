# Portable App Brief

Use this file to describe the app mockups in `images/`.

## Goal

The portable app should let a user configure, run, inspect, and export an F1 race simulation from a local Windows desktop interface.

The app should act as a visual control centre for the existing F1 race simulator project. It should allow the user to select a season, event, session, simulation count, model settings, data sources, weather/race-control modifiers, reliability assumptions, tyre strategy settings, fantasy scoring settings, and output preferences.

The main goal is to make the simulator easier to use without needing to manually edit JSON, CSV, or Python files for every run.

The app should support:

* Running Monte Carlo race simulations.
* Tweaking key model parameters.
* Managing local CSV/config data sources.
* Previewing weather, track, reliability, and strategy assumptions.
* Viewing simulation results in tables, charts, and probability summaries.
* Exporting CSVs, images, snapshots, reports, and Discord-ready output bundles.

---

## Target User

The app is primarily for a technically comfortable F1 fan or analyst who wants to run custom race simulations without working directly in the terminal.

The target user may understand F1 strategy, tyre degradation, weather risk, race pace, safety cars, red flags, and fantasy scoring, but should not need to understand the full codebase to use the app.

The app should work well for:

* Personal F1 race prediction projects.
* Fantasy F1 planning.
* Strategy comparison.
* Backtesting predictions.
* Sharing race-preview outputs to Discord.
* Debugging local simulation data.

---

## Screens

List each image and what it represents.

* `images/01-race-setup.png` - Main race setup screen. Used to select season, event, session, simulation count, random seed, baseline races, historical strategy lookback, output toggles, output folder, weather source, and run readiness.

* `images/02-data-sources.png` - Data management screen. Shows connected CSV/config inputs such as fantasy prices, track profiles, FIA document index, and team power-unit mappings. Includes validation status, row counts, stale/missing file warnings, reload actions, and a table preview.

* `images/03-model-signals.png` - Model signal configuration screen. Allows the user to inspect and adjust how baseline data, current-session data, qualifying pace, race pace, strategy signals, and model uncertainty influence the simulation.

* `images/04-weather-reliability.png` - Weather, chaos, race-control, and reliability screen. Shows weather forecast, race-control context, chaos factor, strategy factor, DNF factor, degradation factor, uncertainty factor, safety-car probability, red-flag probability, wet-race risk, degradation risk, and reliability projections.

* `images/05-results-strategy.png` - Post-simulation results screen. Shows completed simulation outputs including run count, runtime, confidence, safety-car/red-flag probabilities, win probability, podium probability, finish distribution, strategy recommendations, fantasy projections, insights, and export buttons.

---

## Main Workflow

Step-by-step flow through the app.

1. Open the portable F1 Race Simulator app.

2. On the **Race Setup** screen, choose the season, event, session, simulation count, random seed, baseline race count, and historical strategy lookback.

3. Confirm output preferences such as saving prediction snapshots, report images, raw results, and whether to post to Discord.

4. Review the **Data Sources** screen to confirm all required local files are found and valid.

5. If needed, reload data, open the data folder, or inspect CSV previews for track profiles, fantasy prices, FIA documents, and team power-unit mappings.

6. Open **Model Signals** to review or adjust how much weight the simulator gives to baseline performance, current-session data, qualifying signals, race pace, strategy signals, and uncertainty.

7. Open **Weather & Chaos** to review forecast conditions, race-control context, safety-car risk, red-flag risk, wet-race risk, degradation risk, and DNF modifiers.

8. Open **Reliability** to inspect team, driver, and power-unit reliability assumptions, including base DNF probability and effective simulated DNF probability.

9. Open **Tyre Strategy** to compare expected strategies, tyre allocation, tyre status, degradation assumptions, inventory risk, and candidate strategy scores.

10. Open **Fantasy** to review or tune fantasy scoring rules and projected fantasy value.

11. Return to **Race Setup** and press **Run Simulation**.

12. After the simulation completes, open **Results** to review win probability, podium probability, finish distribution, fantasy projections, strategy recommendations, race risk, and model confidence.

13. Use export actions to save CSVs, save a prediction snapshot, generate report images, or post results to Discord.

14. Optionally use **Compare** mode to run multiple race scenarios side-by-side, such as dry race, wet race, high safety-car race, or red-flag scenario.

---

## Inputs

What does the user need to choose or provide?

* Season/year.
* Event name, round number, or `latest`.
* Session type such as `FP2`, `FP3`, `Q`, `SQ`, `S`, or `R`.
* Number of Monte Carlo simulations.
* Optional random seed.
* Number of baseline races.
* Historical strategy lookback years.
* Default overtaking difficulty fallback.
* Output directory.
* Whether to save prediction snapshots.
* Whether to save report images.
* Whether to save raw simulation results.
* Whether to post to Discord.
* Fantasy prices CSV path.
* Track profiles CSV path.
* FIA document index CSV path.
* Team power-unit mapping CSV path.
* Weather source settings.
* Race-control context toggle.
* Track red-flag baseline toggle.
* FastF1 weather toggle.
* Open-Meteo fallback toggle.
* Current-session weighting assumptions.
* Baseline decay settings.
* Practice pace cap.
* Qualifying pace cap.
* Simulation engine constants.
* Reliability/DNF constants.
* Tyre strategy assumptions.
* Fantasy scoring rules.
* Discord webhook configuration, if Discord posting is enabled.

---

## Outputs

What files, charts, reports, or summaries should the app create?

* Simulation results CSV.
* Fantasy projection CSV.
* Driver result table.
* Team result table, if supported.
* Raw simulation rows, if enabled.
* Prediction snapshot JSON.
* Backtesting snapshot.
* Report images.
* Discord-ready summary image.
* Discord post bundle.
* Finish distribution heatmap.
* Win probability chart.
* Podium probability chart.
* Top 10 probability chart.
* Average finish table.
* DNF probability table.
* Reliability risk table.
* Safety-car probability summary.
* Red-flag probability summary.
* Weather and race-control impact summary.
* Tyre strategy recommendation table.
* Fantasy value/xPPM table.
* Model confidence and uncertainty summary.
* Scenario comparison report.
* Local run log.
* Validation log for data sources.
* Error report if a run fails.

---

## Must-Haves

* Portable Windows app that can run locally.
* Clear dark F1-inspired dashboard UI.
* Left-hand navigation between major sections.
* Race setup screen with core run parameters.
* Data source management screen with validation status.
* Ability to reload local data without restarting the app.
* Output toggles for snapshots, images, raw results, and Discord posting.
* Warning when Discord posting is enabled but webhook URL is missing.
* Model signal screen explaining how the forecast is being influenced.
* Weather and chaos screen showing key risk modifiers.
* Reliability screen showing effective DNF probabilities.
* Results screen with win, podium, finish distribution, strategy, and fantasy outputs.
* Export buttons for CSV, snapshot, report images, and Discord.
* Tooltips or help text for technical model parameters.
* Reset-to-default option for advanced model settings.
* Clear distinction between basic controls and advanced tuning.
* App should not require the user to edit Python files manually for normal use.
* App should work with the existing config and CSV structure where possible.
* App should show useful errors instead of only terminal output.

---

## Nice-to-Haves

* Scenario comparison mode.
* Side-by-side dry/wet/safety-car/red-flag scenario comparison.
* Editable CSV table previews inside the app.
* Automatic stale file detection.
* Auto-reload when data files change.
* Data validation log viewer.
* Backtesting screen for previous prediction snapshots.
* Driver/team filtering.
* Fantasy price cap filter.
* Value pick filter.
* Confidence score per output.
* Explanation panel showing why the model favours certain drivers.
* Track map preview.
* Weather timeline.
* Race-control message impact list.
* Model version history.
* Presets for different simulation modes, such as conservative, balanced, chaotic, wet race, high degradation, or fantasy mode.
* Import/export of parameter presets.
* One-click “restore project defaults”.
* Local app settings file.
* Light mode, though dark mode should be the default.
* Ability to open output folder after a run.
* Ability to open generated images immediately after export.
* Discord test message button.
* Run history list.

---

## Local Packaging Notes

Anything important about running locally, EXE packaging, offline use, folders, or Windows security prompts.

* The app should be packaged as a local Windows portable app where possible.
* The user should be able to run the app without installing Python manually, if bundled as an EXE.
* The packaged app should include or locate the required simulator scripts, config files, and data folders.
* The app should use a local writable `outputs/` directory by default.
* The app should support user-selected output directories.
* The app should not write generated outputs into source-controlled folders unless the user chooses to.
* The app should avoid requiring admin permissions.
* The app may trigger a Windows SmartScreen warning if unsigned; this should be documented.
* Any bundled EXE should avoid hardcoded local paths.
* Data paths should be configurable from the app settings screen.
* The app should store user settings in a local config file, such as `app_settings.json`.
* Secrets such as Discord webhook URLs should be stored outside normal exported result files.
* Discord webhook URLs should not be printed into logs unless masked.
* The app should show a clear warning if a webhook is missing, invalid, or blocked.
* The app should work offline for local simulations that do not require live weather or FastF1 fetching.
* If live weather, FastF1, or FIA data is unavailable, the app should fall back gracefully to cached or configured values.
* The app should clearly label whether a run used live data, cached data, or fallback assumptions.
* The app should include a `logs/` folder for run logs and error reports.
* The app should include a `data/` folder for editable CSVs.
* The app should include an `images/` or `reports/` folder for generated visuals.
* The app should include a `snapshots/` folder for prediction snapshots and backtesting.
* The app should include a simple README explaining how to run the portable app, where files are saved, and how to troubleshoot missing data or Discord errors.