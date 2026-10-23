# Portable UI functionality audit

Updated 11 October 2026 with the attached Nocturne racing-red desktop design:
grouped navigation, workflow stages, setup cards, session buttons, simulation
presets, seed shuffle, bounded number steppers, Results drillthrough links and
key/all-column data previews. The app follows verified PC forecasts across
workspaces and updates results plus the default season/event/session; editing
setup pauses following. See [desktop-ui-and-pc-runs.md](desktop-ui-and-pc-runs.md).

The gaps below remain explicit; prototype confidence percentages and sample
forecasts have not been substituted for model outputs.

Rebuilt on 5 October 2026 against the five images under
`docs/mockups/portable-app/images`. The app opens Race Setup by default.
The Simulation Centre remains available from the sidebar for prospective
forecasts, frozen run history, post-race scoring, Discord and Simulink tools.

## Implemented and connected

Tyre Strategy now uses a reference-inspired driver stint chart with compound
colours, solid/dashed/dotted new/used/unknown set lines, recommended and alternative
plans, model-grid/team/stop sorting, stop totals and driver details. The full
recommendation table remains expandable. Saved recommendations do not contain
pit laps: the chart shows sequence, not lap duration or predicted pit windows.
Stop counts follow the displayed sequence, including historical adjustments.

Frontend data checks: `node --test tests/tyre_strategy.test.cjs`.

| Mockup area | Working functionality |
| --- | --- |
| Shell | Dark sidebar, red navigation, event/session/model/weather context cards, responsive panels and original vector icons. |
| Race Setup | Season/event/session, simulation count, seed, baseline races, strategy history, overtaking difficulty, existing calibration/weather controls, live logs and measured runtime for new runs. Each manual run writes to a fresh folder. |
| Output switches | Snapshot, report images and raw-result choices are passed to the pipeline. Manual simulations never automatically send Discord messages. |
| Circuit | Resolved circuit identity and lap count, actual FastF1 telemetry outline when available, explicit missing-data states. Relocated races use the resolved venue. |
| Track Overview | Reads a complete lap from downloaded position telemetry for the selected season/event, without requiring a simulation first. Session fallback is labelled; PRE uses geometry only. Inspect downloaded telemetry opens that same map and archive lap/sector details. Mismatched years or circuit identities are withheld. |
| Data Sources | Four configured CSV cards with validation, row counts, file timestamps and paths; paged previews; external editor/folder actions; reload and validation; optional automatic reload; saved data directory. File timestamps do not prove upstream freshness. |
| Historical Data | Individual years/ranges; detailed FastF1 sessions from 2018 and Jolpica classifications from 1950; optional telemetry; cancellable/resumable workers, per-session provenance/checksums, storage/coverage inventory, paged previews and combined CSV exports. See `HISTORICAL-DATA.md` in the package. |
| Model Training | Select downloaded detailed seasons, check matched Q/R coverage, train separate finish/DNF candidates, cancel workers, review chronological held-out races and baseline metrics, and open saved model/provenance reports. No automatic activation. See `MODEL-TRAINING.md`. |
| Model Signals | Saved effective current-session blend, actual engine signal weights, quality/uncertainty metrics, driver signal distributions and existing model commentary. |
| Weather | Saved observations and five model multipliers; informational future race forecast capture with scheduled/+30/+60/+120-minute start windows, forecast provenance and ensemble coverage. |
| Reliability | Existing historical team/power-unit reliability inputs and modelled driver retirement risk. |
| Results | Win/podium bars, finish-position heatmap, driver strategy estimates, fantasy projections, full summary and saved-run health. Run count and runtime are displayed only when recorded. |
| Compare | Completed manual and Simulation Centre probability runs; matched driver comparison with percentage-point deltas. Frozen forecasts are verified before comparison. Different input sessions are explicit in run labels. |
| Exports | Additive copies of existing CSVs, saved snapshots and images. Missing optional outputs produce a useful explanation. Existing frozen results remain unchanged. |
| Settings | Locally persisted setup/data paths/auto-reload; restore setup defaults; webhook configuration status without exposing its value. |
| Existing tools | Practice, qualifying and race detail views; post-race review; telemetry; prospective forecasting, scoring, verified opt-in Discord uploads and MATLAB/Simulink experiments in Simulation Centre. |

## Functionality the mockups imply but the engine does not yet support

| Gap | Current behaviour | Work needed |
| --- | --- | --- |
| Editable per-session signal weights, baseline decay and pace caps | Actual values/diagnostics are read-only. Existing calibration controls still work. | Run-scoped model configuration, validation and chronological accuracy evaluation before promotion. |
| Calibrated confidence percentage | Shows **Uncalibrated**; heuristic signal quality and uncertainty are available. | Evaluate probability calibration on chronological holdouts; define exactly which outcome confidence describes. |
| Safety-car probability | Shows **Unavailable**. A circuit reference prior is not a calibrated simulated probability. | Explicit safety-car occurrence/duration model and validation against race outcomes. |
| Wet-race probability and delayed-start probability | Conditional weather windows and regional ensemble wet-hour frequency are informational. Delay weights remain unknown and driver probabilities stay unchanged. | Circuit-scale weather calibration and a race-control delay model; validated integration into predictions. |
| Manual chaos/reliability overrides | Saved engine multipliers are shown read-only. | Isolated scenario configuration with clear assumptions; avoid modifying live prediction defaults. |
| Dry/wet/chaos probability presets | Compare actual completed runs. The mockup presets are not presented as working model scenarios. | Scenario-specific weather, disruption, reliability and tyre behaviour; reproducible matched-input runs. |
| Counterfactual tyre strategy win probabilities | Shows existing per-driver strategy estimates. No aggregate strategy win-rate claim. | Evaluate candidate strategies under the same simulated conditions. |
| Official tyre inventory / availability | Existing inferred new/used strategy labels remain. | Reliable per-driver tyre allocation and used-set inputs. |
| Interactive attribution radar / confidence gauges | Existing scores and commentary are shown. | A defined, validated attribution method rather than fabricated percentage contributions. |
| Fantasy scoring editor / current official rules | Displays project scoring constants and available prices/projections. | Versioned season rules and a run-scoped scoring configuration. |
| In-app CSV editing | Opens the configured file in the associated external editor. | Validated editable tables with backup/rollback. |
| One-click PDF/report export | Exports the image and data files already generated. | A composed export report and rendering/visual validation. |
| Cancellation of a Race Setup pipeline | Pipeline runs in the desktop process; wait for completion. Centre jobs retain cancellation. | Move manual pipelines into the existing cancellable worker architecture. |

## Limits and priorities

The appearance and data navigation are rebuilt; this is not evidence of improved
forecast accuracy. Previously archived outputs may lack runtime/simulation-count
metadata. They are not rewritten to invent it.

Prioritise run-scoped scenario controls and chronological validation, then
weather/delay integration, then calibrated confidence and strategy comparisons.
Cosmetic confidence gauges should follow a supported statistical definition.

This remains an unsigned local beta. Build/runtime acceptance on this computer
does not replace clean-Windows testing or establish public-release readiness.
