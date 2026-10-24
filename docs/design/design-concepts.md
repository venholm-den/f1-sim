# Design concepts

Five distinct directions for Race Workbench plus a recommended hybrid. Every concept is built in the playground (`design/playground`) on the same mock data, so they can be compared screen by screen. The concepts restyle and reorganise **existing capabilities**. Anything new is marked **Proposed** and listed in `design-audit.md` §4.

Reference numbers like **[R7]** point to `design-research.md`. Products that were not on Mobbin (Bloomberg Terminal, TradingView, F1 TV, SofaScore) are mentioned only as general genre conventions, never as screen-level claims.

## Shared foundations (all concepts)

- **Seven core screens**: Weekend hub, Prediction, Fantasy, Replay, Driver and team intelligence, Simulation lab, Model evaluation. These replace the 18-item, pipeline-ordered sidebar with goal-ordered destinations. Data, Setup, Training and Settings move behind a "Workshop" menu (still available and unchanged).
- **One focus model.** Click a driver anywhere to focus them across every chart on the screen. Shift-click adds a second driver for comparison, and Esc clears the focus.
- **Honest labels.** Mock, candidate, uncalibrated and unavailable states are always printed next to the number they qualify.
- **Same chart engine.** Hand-written SVG at true pixel size, so there is no new dependency and it works offline in WebView2.

---

## A · Pit Wall (Motorsport Command Centre)

**Philosophy and audience.** An engineer's pit-wall screen: dense, calm, tiled, and keyboard-first. It is for the person who runs the model and wants every number visible together. Colour is used only for meaning, following timing-screen conventions: purple is best overall, green is improved, and amber is caution or the safety car.

**References.** F1 live timing replay [R1] for the tower; OKX multi-pane workspace [R20] for fixed tiling; Descript/VEED shared playhead [R34, R35]; Fey and Vapi key hints [R22, R39]; Linear filter chips [R38].

**Palette.**

| Role | HEX |
| --- | --- |
| Background | `#0B0D10` |
| Panel / panel 2 | `#12151A` / `#181C22` |
| Line / grid | `#262B33` / `#1D2229` |
| Text / muted | `#E6E8EB` / `#8A93A0` |
| Accent (caution, SC) | `#FFB800` |
| Secondary (selection) | `#4FA3FF` |
| Positive / negative | `#2BD47D` / `#FF5A5F` |
| Best (timing purple) | `#B36BFF` |

**Typography.** Inter Tight for UI (13–14 px body, 11 px uppercase panel labels); JetBrains Mono with tabular figures for every number.

**Navigation.** A top bar holds the brand, the event, and tabs 1–7. A footer strip lists the keys and the current focus. There is no sidebar.

**Layouts.** A CSS-grid workspace of named panels, with a different arrangement for each screen. On the replay screen the tower sits on the left, the track and transport in the centre, the position chart and tyres below them, and telemetry on the right. Below 900 px, panels stack in priority order.

**Components.** Panel (header, meta, body), timing tower rows, compact data tables, flag chip, transport bar, lock/exclude chips, key hints.

**Chart styling.** Hairline 1 px grid, no fills behind data, team colour only on focused lines, dashed for each team's second driver. Uncertainty is shown as P10–P90 range bars with a P50 tick.

**Motion.** Lap stepping animates car dots along the track path, about 250 ms per lap at 1× speed. Panels never animate their layout. With reduced motion, positions jump straight to the new lap.

**Strengths.** It has the strongest replay and analyst workflow. It is close to today's Nocturne look, so it is the lowest-risk migration, and its dense tables suit 1440 px.

**Weaknesses.** It is intimidating for casual Fantasy users and leads with numbers rather than answers. Mobile is a stacked compromise.

**Complexity.** Medium. Grid layouts and the focus/playhead controller are the main work.

---

## B · Lights Out (Premium Broadcast)

**Philosophy and audience.** The app as a TV graphics package: cinematic, team-colour led, big numbers, lower thirds. It is for the fan who wants the weekend to feel like an event, and for screenshots shared to Discord.

**References.** F1 live timing [R1] for the tower styling; Apple Sports F1 event and qualifying [R2, R16] for the restrained hero; DAZN lineups [R40] for broadcast overlays; general broadcast-graphics conventions (not taken from Mobbin).

**Palette.**

| Role | HEX |
| --- | --- |
| Background | `#07070C` |
| Panel / panel 2 | `#11111A` / `#1A1A26` |
| Text / muted | `#FFFFFF` / `#A3A3B8` |
| Brand red | `#FF1E3C` |
| Safety car | `#FFC300` |
| Positive / negative | `#3BE38B` / `#FF5A6E` |
| Best | `#C17BFF` |

**Typography.** Barlow Condensed 600–800 for display and numbers (uppercase, tracked); Barlow for body.

**Navigation.** A horizontal broadcast menu with a red underline, and a round badge in the hero.

**Layouts.** A full-bleed hero for each screen (round number, event, headline stat), then panels with square corners. The replay screen is a "stage": the track fills the frame, the tower overlays the left edge, and events appear as lower thirds.

**Components.** Hero banner, broadcast tower (white position block, team stripe), lower-third event card, headline stat, square chips.

**Chart styling.** Thick strokes, team colours always on, square bar ends, labels in condensed caps. Fewer gridlines.

**Motion.** Hero stripes slide in once when a screen loads, lower thirds wipe in on each event, and the tower reorders with a 300 ms ease. With reduced motion, all of this becomes an instant swap.

**Strengths.** It has the strongest identity and the best replay spectacle, and it is easy to share.

**Weaknesses.** Charts are louder than the data needs: always-on team colours make 22 lines hard to read. Dense analysis (lab, evaluation) feels out of place. The heavy hero costs vertical space at 1440 × 900.

**Complexity.** Medium-high. Broadcast polish takes a long tail of detail.

---

## C · Quant Terminal (Quantitative Prediction Terminal)

**Philosophy and audience.** A market terminal for forecasts. Every number has a distribution beside it, every change shows its delta, and a command line drives everything. It is for the power user and model developer.

**References.** OKX workspace [R20]; Fey watchlist deltas and command palette [R21, R22]; Perplexity prediction-market rows with Δ [R24]; Phantom bucketed outcomes [R25]; StackAI small multiples [R28]; Linear facets [R37]. The terminal genre (Bloomberg-style function codes) is referenced only as a convention.

**Palette.**

| Role | HEX |
| --- | --- |
| Background | `#050607` |
| Panel / panel 2 | `#0B0E11` / `#12161A` |
| Text / muted | `#D7DDE3` / `#7D8894` |
| Accent | `#FF9F1C` |
| Data cyan (heat) | `#3BC9DB` |
| Positive / negative | `#4ADE80` / `#F87171` |
| Best | `#C084FC` |

**Typography.** IBM Plex Mono throughout, 12–13 px.

**Navigation.** A command line (`RWB>`) at the top. Typing a screen (`PRED`, `FANT`, `RPLY`, `LAB`), a driver code (focuses that driver) or `LAP 30` works, and function-key style tabs are listed beneath.

**Layouts.** A strict 12-column grid of bordered cells with no gaps. Every panel is titled with a code (for example `B.IQR`, `EVT`, `H2H`).

**Components.** Command input, coded panels, ticker rows with Δ, sparklines, heat matrix, frontier scatter.

**Chart styling.** Single-hue cyan heatmaps, tiny multiples, and value frontiers. Deltas are always shown with a sign as well as colour.

**Motion.** Almost none. Changed values flash their background once for 600 ms (with no flash under reduced motion).

**Strengths.** It has the highest information density and the best Fantasy optimisation view (value frontier, locks). Every action is reachable by keyboard.

**Weaknesses.** It has the steepest learning curve, an all-monospace UI is tiring to read, it barely works on mobile, and its identity is generic.

**Complexity.** Medium. The layout is simple, but the command parser and its discoverability need care.

---

## D · Grid (Modern Consumer Sports App)

**Philosophy and audience.** A friendly, light, card-based, mobile-first app. Each card leads with one plain-language answer ("McLaren's Piastri wins 31% of simulated races"), and the statistics sit behind "Show the maths". It is for Fantasy players and casual fans.

**References.** Apple Sports match with odds [R17]; PL Fantasy create team [R7]; F1 Fantasy picker cost-cap bar [R8]; FotMob team vs team [R11]; WHOOP plain-language insight [R33] (not its rings); Fixtured and F1 schedule [R14, R15]; Kraken big value + small change [R27].

**Palette.**

| Role | HEX |
| --- | --- |
| Background | `#F3F4F6` |
| Card / card 2 | `#FFFFFF` / `#F6F7F9` |
| Text / muted | `#14161A` / `#5B6270` |
| Accent fill / accent text | `#FF3D2E` / `#C8261A` |
| Link and focus | `#2F6BFF` |
| Positive / negative | `#12804A` / `#C62828` |
| Safety car | `#F59E0B` |

**Typography.** Manrope 500–800, at 15 px body size and 28–34 px for answers.

**Navigation.** A bottom tab bar on mobile and a top pill bar on desktop. Segmented controls switch between Win, Podium and Points.

**Layouts.** A single column on a phone and a two- or three-column card grid on desktop. The cost cap stays sticky on Fantasy.

**Components.** Answer card, segmented control, pill bars, "Show the maths" disclosure, driver avatar chip, sticky budget bar.

**Chart styling.** Rounded bars, very few axes, and large labels. Distributions are shown as simple bars rather than ridgelines.

**Motion.** Cards rise 8 px and fade in once on load, and bars grow from zero. Under reduced motion, everything appears immediately.

**Strengths.** It has the best usability and responsiveness and the clearest Fantasy flow. It is the most approachable for new users.

**Weaknesses.** Analytical depth is hidden, and replay is weak on a card layout. Its look resembles many generic sports apps, and it is light only (dark mode would be extra work).

**Complexity.** Medium.

---

## E · Raceline (Experimental Data Experience)

**Philosophy and audience.** An editorial, paper-toned experience in which the weekend is told as a story in chapters. Uncertainty is shown as many possible races (the "fifty futures") instead of one number, and the race itself is drawn as a river of positions. It is for curious readers, and it doubles as a teaching tool for what a Monte Carlo forecast means.

**References.** Strava activity with milestones [R18]; theScore centre spine [R5]; Perplexity watchlist chart legend rows [R23]; MLS typed timeline [R4]. The data-journalism style (annotated figures, side notes) is a general convention and is not taken from Mobbin.

**Palette.**

| Role | HEX |
| --- | --- |
| Paper / card / tint | `#F2EFE8` / `#FBF9F4` / `#E9E4D8` |
| Ink / muted | `#1B1B1F` / `#5F5A50` |
| Vermilion fill / text | `#E4572E` / `#B13F1A` |
| Blue | `#2E5BFF` |
| Positive / negative | `#2F7D4F` / `#B3261E` |
| Safety car (fill only) | `#C98A00` |

**Typography.** Fraunces (serif display headings and ledes), Space Grotesk for UI, Space Mono for numbers.

**Navigation.** A numbered chapter list on the left on desktop, which becomes a horizontal chapter scroller on mobile.

**Layouts.** A single reading column. Each figure has a caption and margin notes, which drop below the figure on narrow screens.

**Components.** Chapter header (number, title, lede), annotated figure, margin note, dot rows, futures grid, river with numbered pins, stacked contribution bar.

**Chart styling.** Ink on paper with one accent. Charts carry direct labels rather than legends, and annotations are part of the chart.

**Motion.** Futures tiles fade in a few at a time (staggered over 400 ms total), and the river line draws from left to right when the page opens. Under reduced motion, both are static.

**Strengths.** It has the most memorable identity and the best explanation of uncertainty. The futures and dot charts are ideas worth keeping in any direction.

**Weaknesses.** It is slow for repeat use, and narrative text has to be written or generated per weekend. Fantasy as a "portfolio essay" is less efficient, and it is the hardest to make data-driven without the copy becoming wrong.

**Complexity.** High. The charts are custom, and the copy needs rules to stay truthful.

---

## H · Recommended hybrid ("Pit Wall + answers")

This combines A's synchronised, keyboard-first workspace with D's answer row at the top of every screen and E's uncertainty pictures (dots, fifty futures and the river) as the signature charts. The palette is A's, lifted slightly for contrast. It is detailed in `design-comparison.md`. It is fully clickable in the playground as "Hybrid ★".

| Role | HEX |
| --- | --- |
| Background / panel | `#0D0F13` / `#14171D` |
| Text / muted | `#ECEEF1` / `#97A0AD` |
| Accent / selection | `#FFB800` / `#5AA9FF` |
| Positive / negative / best | `#2BD47D` / `#FF6166` / `#B36BFF` |

---

## Core experiences

The seven screens below are described as the hybrid builds them. Differences between concepts are noted where they matter.

### 1. Weekend hub (Proposed screen; existing data)

- **Answer row**: favourite and win chance, number of contenders (≥15% win chance), next session, forecast status and the session it followed.
- **Content**: session schedule with finished/next/upcoming states [R15]; dot rows for the top four (where they finish); top-8 win bars with finish ranges behind a disclosure; championship interval chart.
- **Data**: `weekend_briefing.py`, the latest frozen forecast, championship odds (PR #75).

### 2. Prediction dashboard (restyle of Results)

- **Answer row**: most likely winner (and how often someone else wins), likely podium, widest range in the top 8, the favourite's retirement risk.
- **Content**: "fifty futures" grid, classification table (win, podium, points, P10–P90 range), every-position heatmap behind a disclosure, ridgeline of the top 8.
- **Fix**: replaces the 3,000 px Results page with one screen and two disclosures.

### 3. Fantasy workspace (restyle of PR #76)

- **Answer row**: best team's expected points, its P10–P90, the boost pick, spend vs cap.
- **Content**: team card with live points distribution; market chips (click cycles lock in → leave out → auto); risk/reward scatter (expected points vs spread, bubble = price); alternatives with formatted $ and pts.
- **Existing behaviour kept**: 5 drivers + 2 constructors, budget, 2× boost, locks and excludes, alternatives. The transfer planner moves into a "This week vs last week" tab (no new logic).
- **Not shown**: ownership percentages, because the data does not exist.

### 4. Replay (restyle of Session replay)

- **Story line**: the lap and the latest event, in plain words.
- **Content**: timing tower, track map with transport, the race as a river (bump chart with numbered event pins), tyre stints, and fastest-lap telemetry comparison.
- **Proposed**: one lap playhead drives every panel, a derived event list, and keyboard controls (Space, ←/→, Home/End; Shift+←/→ for 5 laps is planned).
- **Fix**: map labels are shown only for focused drivers and the top three, which ends the label collisions.

### 5. Driver and team intelligence (Proposed screen; historical data exists)

- **Answer row**: head-to-head race and qualifying record, best average finish (with retirements), recent podiums.
- **Content**: mirrored head-to-head bars [R10, R12], season form lines with gaps for retirements, field table for the last six races.

### 6. Simulation lab (Proposed controls on top of existing candidates and Compare)

- **Answer row**: which scenario this is, the engine, candidate status, re-run mode.
- **Content**: sliders for safety-car chance, driver noise and grid weight; candidate-engine toggles; "who gains, who loses" diff table with signed deltas; thirty futures under scenario B.
- **Rule**: scenario runs are labelled "Scenario, not a forecast" and can never be frozen as the weekend forecast.

### 7. Model evaluation (Proposed screen; scores exist)

- **Answer row**: rounds where the model beat the grid, skill vs the grid, a calibration summary, rounds scored.
- **Content**: paired RPS per round (model vs grid order), calibration plot for top-three finishes with dot size = forecast count, round-by-round table.

---

## Visualisation specifications

Each entry covers: the question it answers · the data it needs · its encoding · its interactions · its responsive behaviour · how it handles missing data.

| Chart | Question | Data | Encoding | Interaction | Responsive | Missing data |
| --- | --- | --- | --- | --- | --- | --- |
| **Win/podium bars** | Who is most likely to win? | win, podium, points per driver | Horizontal bar length from 0 to 100%, with the label and value inline | Click to focus | Top 8 on mobile, top 12 on desktop | A driver with no runs shows "—" and no bar |
| **Finish range** | Where will each driver finish? | P10, P25, P50, P75, P90 | Thin P10–P90 line, thick P25–P75 bar, P50 tick, grid position as a hollow marker | Hover for values, click to focus | Rows compress to 18 px; the axis switches to P1/P5/P10/P15/P20 ticks | If quantiles are missing, show the average finish dot only and label it "range unavailable" |
| **Quantile dots** | How spread out is one driver's result? | position matrix (50 sampled races per driver) | 50 dots stacked at finishing position; red = retirement | Hover for "1 in 50 races" | Dot radius fits the row height | If there is no matrix, hide the chart and fall back to the range |
| **Fifty futures** | What do individual possible races look like? | sampled finishing orders (top 3 per sim) | Tile per simulated race; three bars in team colour for P1–P3 | Focus a driver to highlight their tiles | 10 columns on desktop, 5 on mobile | Needs stored per-sim orders. If the run only kept the matrix, sample orders from the matrix and label them "approximate" |
| **Position heatmap** | What is the chance of every position? | position matrix | Single-hue sequential scale with % values in cells; empty below 0.5% | Hover a cell, click a row | Scrolls horizontally on mobile with a sticky driver column | An empty cell means less than 0.5%, which is explained in the legend |
| **Ridgeline** | How do the distributions compare in shape? | position matrix | Smoothed density per driver, with a shared baseline per row and a 30% overlap | Focus dims the others | Top 8, with height derived from width | Hidden if there are fewer than 500 sims (too noisy) |
| **Championship interval** | Who can still win the title? | current points, P10–P90 expected final points, title % | Dot for points now, bar for the range, title % at the end of the row | Click to focus | Top 6 on mobile | Clinched/eliminated drivers show a text badge instead of a bar |
| **Risk/reward scatter** | Which Fantasy picks give most points for least swing? | fantasy mean, P10–P90 spread, price | x = spread of outcomes (standard deviation of fantasy points), y = expected points, area = price | Click to lock/exclude, hover for details | Labels only for the top 8 by value on mobile | Assets without a price are excluded and counted in a footnote |
| **Team points histogram** | How does my team score across races? | per-sim team totals | Histogram with P10/P50/P90 markers | Re-renders on any lock change | Full width | If there are no per-sim totals, show the P10–P90 bar only |
| **Track map** | Where is everyone on this lap? | resampled position telemetry or the lap fraction | Car dots in team colour on the track path, labels for focused drivers and the top 3 | Scrub; click a car to focus | 230 px high on mobile | Without position data, place cars by lap fraction along the path and label it "approximate positions" |
| **River (bump chart)** | How did the order change through the race? | position per lap per driver, track status, pit and retirement laps | Line per driver, height = position; numbered pins for SC, retirements and fastest lap; SC band shaded | Focus lines, click a pin to jump to its lap, show the cursor at the current lap | Top 10 lines on mobile | Missing laps break the line (no interpolation); a retirement ends the line with ×. Pins after the current lap are hidden |
| **Tyre stints** | Who is on what tyre, and when did they stop? | compound and tyre life per lap | Horizontal stint bars coloured by compound with S/M/H letters (not colour alone); SC band shaded | Cursor follows the playhead | Rows shrink to 12 px | An unknown compound is shown as a hatched grey bar labelled "?" |
| **Telemetry trace** | Where does one driver gain on another? | speed, throttle and brake by distance for two laps | Two speed lines (A solid, B dashed) with a delta strip underneath | Hover for a distance crosshair | Speed only on mobile | Only drawn when both laps are flagged accurate; otherwise "telemetry unavailable for this lap" |
| **Head-to-head bars** | Who beat whom? | race and qualifying finishes per round | Mirrored bars, with the winner in bold | Swap drivers | Stacks on mobile | Rounds where either driver did not start are excluded, with the count noted |
| **Form lines** | How has form moved over the season? | finish per round | Line per driver; gaps for retirements; y-axis inverted (P1 at the top) | Focus | 8 most recent rounds on mobile | Gaps, not zeros |
| **Paired RPS** | Did the model beat simply copying the grid? | RPS model, RPS grid per round | Paired dots joined by a line; grey = grid | Hover a round | Horizontal scroll | Unscored rounds are omitted and the count is shown |
| **Calibration** | When the model says 30%, does it happen 30% of the time? | binned forecast probability, observed rate, count | Dots on a 45° reference line, area = count | Hover a bin | Square | Bins with fewer than 10 forecasts are hollow and labelled "few forecasts" |

**Excluded on purpose.** There are no gauges or rings for probabilities [R32, R33], no 3D charts, no dual y-axes, no truncated bar baselines, and no pie charts for shares other than the Fantasy contribution bar (one straight stacked bar).

---

## Motion and interaction

| Interaction | Behaviour | Reduced motion |
| --- | --- | --- |
| Screen change | 120 ms content fade | Instant |
| Driver focus | Others fade to 25% opacity over 150 ms; the label shows "Focus: PIA" | Instant opacity change |
| Replay play | Cars ease along the path, about 250 ms per lap at 1× (½×, 2× and 4× also available) | Play still works but jumps lap by lap with no easing; autoplay is off by default |
| Replay step | Tower rows reorder with a 200 ms translate | Instant reorder |
| Lab re-run | Old values stay until the new run lands, then changed cells flash once | No flash; changed cells keep a ▲/▼ marker |
| Fantasy lock | The chip cycles state and the team card updates in place | Same, with no transition |

**Keyboard map (playground-verified).**

| Key | Action |
| --- | --- |
| `1`–`7` | Switch screen |
| `Space` | Play or pause the replay |
| `←` / `→` | Step one lap back or forward |
| `Shift`+click | Add a driver to the comparison |
| `Home` / `End` | Jump to the start or finish of the replay |
| `Enter` on a driver row | Focus that driver (with `Shift` to compare) |
| `Esc` | Clear the focus |
| `Enter` in the C command line | Run the command |

`Shift`+`←`/`→` (5 laps), `/` to open the command palette and a `?` cheat sheet are planned for production.

Focus rings are always visible (2 px, in the selection colour). Every chart has a text alternative: either a `role="img"` label summarising it, or a "View as table" disclosure.
