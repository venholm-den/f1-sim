# Design audit: Race Workbench today

Audit of `main` at `1409302` (after PR #75 championship odds and PR #76 Fantasy team picker). No production code was changed for this audit or for the redesign concepts.

## 1. Stack and architecture

| Area | What exists |
| --- | --- |
| Shell | Portable Windows app: Python + PyInstaller + **pywebview** (Edge WebView2, so a current Chromium engine). `portable_app/web_main.py` starts it; `web_backend.py` exposes Python methods to JavaScript through the pywebview bridge (`bridge.js`). |
| Frontend | **Vanilla HTML, CSS and JavaScript.** No framework, bundler or Node dependency. One large `index.html` (≈53 KB) holds every view as a `<section class="view">`; behaviour is split across `app.js`, `workbench.js`, `replay.js`, `fantasy.js`, `championship.js`, `tyre-strategy.js`, `historical.js`, `training.js` and `pc-runs.js`. |
| Second app | **Simulation Centre** (`centre.html`, `centre.js`, `centre.css` + `centre-nocturne.css`): forecasts, run history, post-race scoring, Discord and Simulink tools. Separate page, separate layout, its own canvas chart. |
| Styling | One "Nocturne" token set in `app.css` (`--bg #161826`, `--panel #232532`, `--red #e57669`, `--green`, `--amber`, `--blue`, `--violet`) plus feature sheets (`replay.css`, `tyre-strategy.css`). Segoe UI / Bahnschrift. Inline SVG icons. |
| Charts | Hand-written: HTML/CSS bars (`renderBarChart`, `renderProbabilityChart`), finish-range strip (`renderFinishRange`), heatmap table (`renderHeatmap`), SVG tyre-stint chart (`tyre-strategy.js`), SVG replay map, lap chart and telemetry traces (`replay.js`), one canvas chart in the Centre. No chart library. |
| Tests | `node --test tests/tyre_strategy.test.cjs` for frontend data rules; Python tests cover backend services. |

Implication for the redesign: any direction must work as **static HTML/CSS/JS inside pywebview, offline, with fonts bundled locally**. A framework migration (React/Tauri) is listed in `docs/architecture.md` as a long-term option, not a current plan, so the playground uses the same vanilla stack.

## 2. Navigation and journeys

The sidebar is organised by **workflow stage**, not by user goal:

1. **Data**: Data sources, Historical data, Model training
2. **Setup**: Race setup (default landing view)
3. **Analyse**: Results, Model signals, Weather & risk, Reliability, Tyre strategy, Fantasy, Compare, Championship
4. **Sessions**: Practice, Qualifying, Race review, Track map, Session replay
5. Settings, plus a link out to the Simulation Centre.

That is 18 views plus the separate Centre. Main journeys today:

- **Run a forecast**: Race setup → run (log in the page) → Results. Or Simulation Centre → Forecast next race (frozen run) → later scoring.
- **Read a forecast**: Results (win/podium bars, finish range, driver table, heatmap, strategy, Fantasy projections, insights, run health).
- **Fantasy**: Fantasy view → team picker (5 drivers + 2 constructors, budget, boost, lock/exclude chips) → transfer planner → alternatives.
- **Replay**: Session replay → pick an archived session → map + running order + lap chart + lap telemetry comparison.
- **Model work**: Data sources, Historical data, Model training, Model signals, Compare (A/B runs), candidate engines in Race setup.

## 3. Data the UI can actually show

Only these are treated as existing capabilities in the concepts.

| Domain | Fields available (source) |
| --- | --- |
| Race forecast | Per driver: win, podium, points, top-10, DNF chance, average finish, P10/P25/P50/P75/P90 finish, full position matrix, average points, fantasy points (mean, P10, P90). Run metadata: sims, seed, runtime, input session, model, frozen status. (`simulation_summary.csv`, `position_matrix.csv`, run JSON) |
| Explanations | `prediction_reasoning.csv`: grid source, model inputs, time-loss components; model commentary text; signal weights and quality (`model_signals.py`). |
| Strategy | Predicted tyre sequence per driver (no pit laps), stop count, heuristic confidence, history-adjusted plan; estimated tyre set ledger. |
| Weather & risk | Session weather multipliers, red-flag chance, informational race-window forecast (scheduled/+30/+60/+120 min). Safety-car probability is **not** a calibrated model output (shown as Unavailable). |
| Reliability | Team/power-unit reliability inputs, modelled driver retirement risk. |
| Fantasy | Official prices (`data/fantasy_market`), scoring constants, projected points, team picker with budget/boost/locks, transfer planner with penalty, alternatives, team points distribution. **No ownership / "% picked" data.** |
| Championship | Drivers' and constructors' title odds, top-3 chance, expected final points with P10–P90, clinched/eliminated, remaining calendar. |
| Replay | Archived FastF1 sessions: laps (time, compound, tyre life, pit in/out, deleted, accurate), results, track status changes (yellow, SC, VSC, red), resampled position telemetry for the map, per-lap car telemetry (speed, throttle, brake, gear, RPM, DRS). Telemetry comparison already colours a mini-sector track map by the faster lap; sector information also appears in the Track map and session views. **Not live timing.** |
| Evaluation | Post-race scoring: ranked probability score, position log score, head-to-head Brier (`race_scores.py`); backtests and calibration reports; prospective trials; promotion evidence. |
| Weekend | Upcoming weekend briefing (`weekend_briefing.py`): schedule, track reference. |

## 4. Existing capabilities vs proposed additions

| Capability | Today | In the concepts |
| --- | --- | --- |
| Win/podium/points/DNF probabilities, finish ranges, position matrix | Yes | Restyled; shown as quantile dots, "fifty futures", ridgelines |
| Fantasy team picker, boost, locks, alternatives, team distribution | Yes (PR #76) | Restyled; risk/reward scatter and value frontier are new views of existing numbers |
| Championship odds with P10–P90 | Yes (PR #75) | Restyled as an interval chart |
| Replay map, running order, lap chart, telemetry | Yes | Adds synced scrubbing across tower/map/bump/tyres, event pins, keyboard control |
| Event timeline from track status + pit flags + results | Data exists, no unified list | **Proposed**: derived event list (SC, pits, retirements, fastest lap) |
| Weekend home | Partial (briefing service, Race setup context strip) | **Proposed**: a hub screen |
| Driver/team intelligence (season form, head-to-head) | Data in historical library, no dedicated view | **Proposed** |
| Scenario lab (adjust parameters, compare A/B) | Candidates + Compare exist; parameters mostly read-only | **Proposed**: run-scoped scenario controls (the docs already list this as a gap) |
| Model evaluation dashboard | Scores exist in Centre/backtests | **Proposed**: one accuracy screen |
| Predicted ownership, live timing, counterfactual strategy win rates, calibrated SC probability, sector timing | No | **Not shown as features.** Listed as future data work only |

## 5. Usability problems found

Evidence: the current screenshots in the project folder (`ui-review/after/*`, `replay/*`, `fantasy-picker/*`, `championship/*`) and the code above.

### High

1. **Navigation follows the pipeline, not the question.** A user who wants "who wins Sunday" or "what team should I pick" lands on Race setup and must know that answers live under Analyse → Results or Fantasy. There is no home that summarises the weekend.
2. **Results is one very long page.** KPIs, two charts, the driver table, heatmap, strategy, Fantasy and insights all stack vertically (≈3,000 px at 1440 wide). There is no hierarchy between the headline answer and supporting detail.
3. **Two apps, two layouts.** The Workbench and the Simulation Centre have different shells and chart styles, and forecasting is split between them.
4. **Charts do not talk to each other.** Selecting a driver in the replay highlights them in the running order and lap chart, but nowhere else in the app. Results, Fantasy and Championship have no shared focus.

### Medium

5. **Uncertainty is mostly shown as point values.** Win bars and Fantasy projections lead with single numbers; the range chart exists but is secondary. Readers over-trust "38.5%".
6. **Replay map labels collide** when cars bunch (see `replay/replay-top.png`), and there is no unified event list, keyboard play/scrub or tyre-strategy view synced to the replay lap.
7. **Fantasy picker is table-heavy.** Chips for 33 assets, then a table, then KPIs and alternatives. Risk (P10–P90) is present but visually equal to price.
8. **Dense tables lack units and grouping** in places (e.g. alternatives show `99.200` / `-10.270` without currency or points formatting).
9. **Mobile is an afterthought.** Breakpoints exist (1180/900/850/620/500 px) but the sidebar-plus-panels layout was designed for desktop; on a phone the context strip disappears and long tables scroll sideways.
10. **No keyboard model** beyond Enter on some rows.

### Low

11. Brand is generic ("Race Simulator · Monte Carlo workbench"); logo work exists in the project folder but has no visual system around it.
12. Colours for meaning are inconsistent between views (red is both brand accent and "Race" session marker and DNF).

## 6. What to keep

- Honest labelling: "Uncalibrated", "Unavailable", "not a leakage-free backtest", candidate badges. Every concept keeps this tone.
- Team-colour stripes and dashed second-driver lines (already in replay).
- Frozen-forecast provenance and run health.
- The vanilla stack and offline-first packaging.
