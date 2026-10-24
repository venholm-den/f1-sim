# Implementation roadmap

**Nothing in this roadmap starts until Kyle picks a direction.** The phases assume the recommended hybrid (H). Phases 1–3 would be the same for A or D, and only the styling of phases 4–6 would change.

Each phase is one or two PRs. Each one is shippable on its own, behind no flags, and keeps the vanilla HTML/CSS/JS stack inside pywebview.

| Phase | Scope | Changes | Risk | Size |
| --- | --- | --- | --- | --- |
| **0. Confirm** | Kyle picks a direction. Optionally, 3–5 users try the playground on two tasks ("pick a Fantasy team", "find when the SC changed the race") | None | — | S |
| **1. Foundations** | Tokens from `design-system.md` in `app.css` (alongside Nocturne, mapped by variable name); locally bundled Inter Tight and JetBrains Mono; base chart helpers (`charts.js` patterns: range, bars, heat) as a shared module | `portable_app/web/app.css`, new `fonts/`, new `charts-core.js` | Low: visual only | M |
| **2. Shell and navigation** | Top bar with seven destinations, a "Workshop" menu for Data, Setup, Training and Settings, a footer key strip, and global driver focus (`[data-driver]`, Shift-click, Esc). Existing views are re-parented, not rewritten | `index.html`, `app.js` | Medium: every view moves. Needs a screenshot pass across all 18 views | M |
| **3. Prediction + Weekend hub** | Answer rows; the Results page split into the prediction screen plus disclosures; the hub assembled from `weekend_briefing.py`, the frozen forecast and championship data; dots, ridge and (if per-sim orders are stored) fifty futures | `workbench.js`, `championship.js`, possibly the backend storing a sample of 50 finishing orders per run | Medium: needs a small backend addition for futures | L |
| **4. Fantasy** | Restyle the PR #76 picker: market chips with lock/exclude states, a sticky budget bar, the risk/reward scatter, and alternatives with formatted units. No change to the optimiser | `fantasy.js` | Low | M |
| **5. Replay** | One playhead driving the tower, map, river, tyres and telemetry; a derived event list (track status, pits, retirements, fastest lap); keyboard controls; labels only for focused drivers and the top 3 | `replay.js`, `tyre-strategy.js` | Medium: performance at 4× speed with 20 cars. Throttle to `requestAnimationFrame` | L |
| **6. New screens** | Driver and team intelligence (historical library), the model evaluation screen (`race_scores.py`, backtests), and lab scenario controls on top of the existing candidates and Compare | New `intel.js`, `evaluation.js`; `pc-runs.js` for the lab | Medium: lab runs must never be frozen as forecasts | L |
| **7. Centre merge** | Fold the Simulation Centre's forecast and scoring tools into Evaluation and the Lab, keeping the Discord and Simulink tools in the Workshop | `centre.*` | Medium | M |

## Guardrails for every phase

- **CI stays green.** pytest and the `node --test` suites in CI must pass. Each phase adds `node --test` coverage for the data shaping it introduces: answer-row values, event derivation and focus state.
- **Screenshots.** Before/after screenshots at 1440 × 900 and 390 × 844 go in each PR.
- **Reduced motion and contrast.** These are checked for each PR against `design-system.md` §4.
- **No invented data.** Ownership, live timing and a calibrated safety-car probability stay out until real data exists.
- **The playground stays a reference.** `design/playground` is never imported by the app.

## Status

- **Direction:** Kyle chose **L · Broadcast hybrid**, which applies B's look to the hybrid's screens.
- **Phase 1 is done.** It covers:
  - Broadcast tokens in `app.css` and `centre.css`, so the Workbench and the Simulation Centre share one palette.
  - Barlow and Barlow Condensed bundled in `portable_app/web/fonts/` (SIL OFL 1.1, about 160 KB) and loaded through `fonts.css`. The browser-mode server serves them too.
  - Condensed upper-case page and panel headings.
  - Solid red primary buttons using `--red-fill` `#E0122F`, so white text meets 4.5:1.
  - Hard-coded Nocturne tints replaced with broadcast equivalents.
- **Phase 2 is done.** It covers:
  - A broadcast top bar (red rule, Barlow Condensed) replacing the sidebar, with six destinations: Weekend, Predict, Fantasy, Replay, Championship and Lab. Drivers and Accuracy arrive with their screens in phase 6.
  - Section tabs under the bar for destinations with more than one view, and a Workshop menu for Data Sources, Historical Data, Model Training and Settings. All 18 existing views are kept and re-parented, not rewritten.
  - Shared driver focus: click a driver row to highlight it, Shift-click to compare two, Esc or the focus chip to clear. Covered by `tests/shell_focus.test.cjs`.
  - Keys 1–6 switch destination. The footer key strip is deferred to phase 5, where replay adds its own keys.
- **Phase 3 is done.** It covers:
  - A Weekend overview, now the screen the app opens on, with an answer row (favourite, contenders, championship leader, forecast), quantile dots for the top four, win chance, the saved briefing's session times and title odds. Session times are read from `outputs/weekend_briefings` by `saved_briefing`, without fetching anything.
  - An answer row on Results (most likely winner, likely podium, widest range in the top 8, retirement risk), with run details, the heatmap, strategy, Fantasy and insights moved under "Show the maths".
  - Every answer is computed in `forecast.js` and covered by `tests/forecast_answers.test.cjs`.
  - **Deferred:** fifty futures and the ridge chart. Frozen forecasts keep only the summary and position matrix, not per-simulation orders, so fifty futures needs the backend to store a sample of orders first. The quantile dots already show each driver's distribution, so the ridge was left out.
- **Phase 4 is done.** It covers:
  - An answer row above the picker: the best team's expected points, its usual range (P10 to P90), the boosted driver and the spend, or the gain over your own team when one is entered.
  - A sticky budget bar with the budget, boost switch, a spend meter and the Pick button.
  - Market chips grouped into drivers and constructors, showing price and expected points, with explicit IN and OUT states and the best team marked.
  - A risk and reward scatter: expected points against the spread of simulated scores, falling back to price when floors and ceilings weren't saved.
  - Alternatives with prices in $m and the gap to the best team in signed points. Projections and scoring rules moved under "Show the maths". The optimiser is unchanged. Covered by `tests/fantasy_view.test.cjs`.
- **Phase 5 is done.** It covers:
  - A race event list beside the running order, derived from timing only: safety car, VSC and red flag starts, track clear, pit entries with the new compound, cars that stop two or more laps before the end, and each new fastest lap. Clicking an event jumps five seconds before it and focuses that driver. The current event follows the playhead.
  - Event pins on the scrub bar, coloured by kind.
  - Keyboard controls: Space plays or pauses, ← and → step a lap, Shift with an arrow moves 10 s, comma and full stop change speed, and Esc clears the focus. A key strip under the controls lists them.
  - Map labels only for the top three and the focused driver, and familiar team colours where the team is known. Covered by `tests/replay_events.test.cjs`.
  - The playhead already drove the map, running order, flag and lap chart cursor; telemetry stays a separate lap comparison.
- **Not yet changed:** the new screens, which are phase 6. The replay driver palette in `replay.js` also still uses the old colours; it moves in phase 5.
