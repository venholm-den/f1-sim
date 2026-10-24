# Design research

## Method

- **Mobbin MCP** was connected for this work and used for 16 searches (iOS and web). Every reference below links to a screen the MCP actually returned and that was looked at. Nothing here is described from memory of an app.
- Searches covered sports/live (F1, match centres, fantasy, schedules, head-to-head), finance/analytics (trading workspaces, prediction markets, KPI dashboards), media (video timelines and scrubbers) and productivity (Linear filters, command palettes).
- Not found on Mobbin in usable form: Bloomberg Terminal, TradingView chart workspace, SofaScore and F1 TV. Patterns from those products are discussed only in general terms in `design-concepts.md` and are marked as such; no screen-level claims are made.

## References

Each entry: what it is, why it works, the pattern, how it translates to Race Workbench, accessibility or usability limits.

### Sports and live experiences

| # | App · screen | Why it works | Pattern | Translation to F1 | Limits |
| --- | --- | --- | --- | --- | --- |
| 1 | [Formula 1 · Live timing replay (Laps tab)](https://mobbin.com/screens/539a91cb-9ac0-4908-8605-51a4bddd6260) | Familiar timing tower: position, team stripe, gap, lap time, tyre. Race-control message pinned at the bottom. | Fixed-column timing tower + sticky race-control ticker | Replay running order; race-control strip derived from track status | Red "PIT" text on black is the only signal for pit state; very small type |
| 2 | [Apple Sports · F1 qualifying](https://mobbin.com/screens/d0a2a849-6aae-44b5-9b03-22320e7f9ff1) | Top-3 heads above a clean ranked list, gap column only. Calm, readable | Podium header + minimal list | Weekend hub "our pick" and prediction list | Little room for uncertainty; one number per row |
| 3 | [Apple Sports · Play-by-play](https://mobbin.com/screens/31114dc5-2276-4382-9724-5eec2c8b237b) | Event cards with time stamps; "All plays / Key plays" toggle | Filterable event feed | Replay event list with "key events only" (SC, pits, DNF, fastest lap) | Colour bar is the only type cue |
| 4 | [MLS · Play-by-play timeline](https://mobbin.com/screens/14191cd2-7fec-472c-bebb-f1f73243f983) | Vertical timeline with icons for event type; highlight cards for big moments | Spine timeline, emphasised key events | Race narrative in concept E; event pins on the position chart | Long scroll for a long match/race |
| 5 | [theScore · Scorecast](https://mobbin.com/screens/323313dd-fbdd-4a33-a292-14a9c07d8243) | Centre spine, events left/right by team; running score in margin | Two-sided timeline | Head-to-head race story (driver A vs B events) | Hard to scan without icons |
| 6 | [FotMob · Commentary](https://mobbin.com/screens/6aeaca7f-77fd-45a3-8954-ec8a053d35b5) | Minute badges, typed cards (highlight, substitution) | Typed event cards | Event list styling | Text-heavy |
| 7 | [Premier League · Fantasy Create Team](https://mobbin.com/screens/6e9ad774-96bb-4ef4-b48c-92dac0bd4712) | Bank, deadline and "squad complete" state are always visible; players on a pitch | Persistent budget bar + spatial line-up | Fantasy team sheet with cost-cap bar | Pitch metaphor doesn't fit F1; price chips low contrast |
| 8 | [Formula 1 · Fantasy driver picker](https://mobbin.com/screens/b077c21f-b015-4044-8a6b-0593ca7db8ea) | Cost cap bar, Drivers/Constructors tabs with slot dots, price + price change, % picked, add button | Picker list with cap meter | Fantasy builder. We have prices and projections, **not % picked**; show expected points and range instead | Team-colour tiles carry meaning only by colour |
| 9 | [Formula 1 · Fantasy predictions question](https://mobbin.com/screens/f5bbde2d-83eb-423d-821f-b4dbb3e026fe) | Countdown, progress dots, one question at a time, chip | Stepper with countdown | Weekend hub countdown | Not relevant to forecasting directly |
| 10 | [Premier League · Player comparison](https://mobbin.com/screens/7bc475f9-158f-4d39-a25e-11730e237d5c) | Mirrored stats, winner in bold, grouped sections | Mirrored stat table | Driver head-to-head | Bold-only winner cue |
| 11 | [FotMob · Team vs team](https://mobbin.com/screens/dc306981-a03f-4e3e-8526-7943a724039f) | Coloured pills mark the better side; previous meetings summary | Head-to-head with outcome summary | "PIA 11–7 NOR" summary + stat rows | Pill colours depend on team colours |
| 12 | [MLS · Match stats](https://mobbin.com/screens/ec7d73d7-f171-4997-8011-a87b8ec2e0f5) | Paired bars per stat in team colours | Paired bar comparison | Quali vs race, driver vs driver | Gradient bars, decorative |
| 13 | [Hevy · Comparison](https://mobbin.com/screens/0f91d578-7a46-466f-897c-08a505b17507) | Two bars per metric with % difference | Bar pair + delta | Consumer-style head-to-head (concept D) | Colour only for who is who |
| 14 | [Fixtured · Formula 1 schedule](https://mobbin.com/screens/11d10641-8ab2-4157-9269-eeadff8b16a6) | Day column + session cards | Day-grouped schedule | Weekend hub sessions | Saturated red cards everywhere |
| 15 | [Formula 1 · Schedule](https://mobbin.com/screens/02427d88-0254-4726-b3ff-b8c2ad39beed) | My time vs track time toggle; finished state per session | Session list with state | Session states (done/next) | — |
| 16 | [Apple Sports · F1 event](https://mobbin.com/screens/db477854-16fa-4304-b201-a767e565b618) | Quiet event sheet: schedule, coverage, location | Event detail sheet | Hub event header | — |
| 17 | [Apple Sports · Match with odds](https://mobbin.com/screens/953205ab-e643-42d3-a03f-4b177ec74396) | Score first, then odds, then paired stat bars | Answer first, details below | Grid concept's "answer, then show the maths" | Odds shown as decimal only |
| 18 | [Strava · Activity detail](https://mobbin.com/screens/125cbc4d-55cc-4abc-82d0-4ff489ed616e) | Map with milestone markers, then a stat grid and achievements | Map + annotated markers + stat grid | Replay map with pinned events; driver intel stat grid | Map dominates small screens |
| 19 | [Runna · Splits](https://mobbin.com/screens/1e34544e-d75a-4ecf-88f1-46623830bf1b) | Splits table with signed deltas in green/red | Delta column | Lap-time deltas, A/B diffs | Colour-only delta sign mitigated by +/− |

### Finance and analytics

| # | App · screen | Why it works | Pattern | Translation | Limits |
| --- | --- | --- | --- | --- | --- |
| 20 | [OKX · Trading workspace](https://mobbin.com/screens/f8b9edc8-dc9e-4cf6-ab03-a802e3112275) | Fixed multi-pane layout: markets list, chart, order book, trade form | Dense tiled workspace | Pit Wall and Quant Terminal layouts | Overwhelming for casual users |
| 21 | [Fey · Home with watchlist](https://mobbin.com/screens/8487cb92-3969-4f21-a847-26177466cf9a) | Dark, quiet hierarchy; watchlist with signed deltas | Watchlist with change column | Forecast monitor with "Δ since last forecast" | Low-contrast greys |
| 22 | [Fey · Command palette onboarding](https://mobbin.com/screens/ff52ac90-4d18-4765-98da-df1e362a5ee1) | Shortcut letters next to every command | Command palette with key hints | Quant Terminal command line; global shortcuts | Discoverability needs onboarding |
| 23 | [Perplexity Finance · Watchlist movers](https://mobbin.com/screens/471f9aa4-b86c-4eb8-bddf-6f7a36639782) | Multi-line chart with matching legend rows and time-range pills | Linked legend rows ↔ lines | Lap times / form lines with clickable legend | Many similar hues |
| 24 | [Perplexity · Prediction markets](https://mobbin.com/screens/8b30d31f-09b1-4ecc-9018-821992bea494) | Outcome rows with probability and change since last update | Probability + delta rows | Win chance with Δ since previous session's forecast | No uncertainty band |
| 25 | [Phantom · Predict](https://mobbin.com/screens/7c091064-88f6-422b-91bf-fe3904cbfecf) | Bucketed outcomes list | Binned outcome probabilities | Cumulative P(≤k) table | Repeated values look broken |
| 26 | [Origin · Market watch](https://mobbin.com/screens/bd2e77b9-e42e-44af-bfc6-e376829a6586) | Sparklines in summary cards; side drawer watchlist | Card + sparkline + drawer | Driver cards with form sparkline | — |
| 27 | [Kraken · Portfolio](https://mobbin.com/screens/96301422-fcd8-40f6-899d-7aab6d69260f) | Big value, small change, time pills, action panel docked right | Hero number + docked action | Fantasy expected points + docked picker | Chart unlabeled |
| 28 | [StackAI · Analytics](https://mobbin.com/screens/03fb91f0-89d0-45e6-ada1-34d533a3febf) | Small-multiple KPI charts, sortable table below | KPI small multiples | Accuracy screen scorecards | Tiny axis labels |
| 29 | [Mintlify · Analytics](https://mobbin.com/screens/03b084b9-d5ed-41be-a9ca-43445af854f2) | KPI tiles with selected state driving the chart | Tile-selects-chart | Evaluation metric tiles | — |
| 30 | [Posh · Overview](https://mobbin.com/screens/a5dfb295-302e-4298-83e0-d78a646e2c15) | Period pills, crosshair tooltip | Crosshair + tooltip | Scrubbable charts | Smoothed curve can mislead |
| 31 | [Binance · Compare traders](https://mobbin.com/screens/c9082a3f-e279-4922-b385-e51609bf94d5) | Column per entity, "+" to add | Add-to-compare columns | Scenario A/B (and C) comparison | Horizontal scroll on mobile |
| 32 | [WHOOP · Recovery detail](https://mobbin.com/screens/ac63ec03-31a3-4496-a433-1bb84062cad2) | One score, then contributing metrics with baseline under each | Score + drivers + baseline | Confidence card with "vs season average" | Ring gauge hides scale; avoid for probabilities |
| 33 | [WHOOP · Home](https://mobbin.com/screens/2a304724-c00c-49b4-861d-0af230d8827e) | Three rings + plain-language insight card | Plain-language insight | Grid concept answer cards | Rings for probabilities would be decorative |

### Media and productivity

| # | App · screen | Why it works | Pattern | Translation | Limits |
| --- | --- | --- | --- | --- | --- |
| 34 | [Descript · Timeline](https://mobbin.com/screens/8e7d9e06-8573-444d-978c-0d93e2341df3) | Transport controls + time readout + zoom on one bar; tracks stacked | Transport bar + stacked tracks | Replay scrubber over position, tyre and event tracks | Dense for touch |
| 35 | [VEED · Editor](https://mobbin.com/screens/7b23c07d-8202-4a67-a768-7d05bd891f05) | Coloured clips per track, playhead through all tracks | Shared playhead | One replay cursor through bump, tyres and telemetry | — |
| 36 | [Vimeo · Editor](https://mobbin.com/screens/32f497f7-6e8e-453b-86b0-221373632881) | Simple transport, timecode, zoom slider | Minimal transport | Consumer replay controls | — |
| 37 | [Linear · Issue filters](https://mobbin.com/screens/ed670cda-0527-4716-a1a6-0159f12c4f42) | Filter menu with typed facets and counts | Faceted filter menu | Driver/team/session filters; saved views | Many nested menus |
| 38 | [Linear · Active filter chips](https://mobbin.com/screens/9dab540b-f7d4-47d4-be77-5facc75f89fa) | Applied filters as removable chips; "14 hidden by filters" | Filter chips + hidden count | Fantasy locks/excludes as chips with "n assets excluded" | — |
| 39 | [Vapi · Command palette](https://mobbin.com/screens/593d7acd-2e16-4365-bcd6-02ce52f48f3b) | Recent + all pages, key hints in footer | Palette with sections | ⌘K jump to driver/screen | — |
| 40 | [DAZN · Lineups](https://mobbin.com/screens/a48a5a9b-d452-4832-99b0-29137b70f6f3) | Spatial line-up with event badges | Spatial roster | Broadcast team sheet (concept B) | Pitch metaphor not used |

Also returned and reviewed but used only as background: [theScore leaders](https://mobbin.com/screens/980d2fe2-84ea-4663-9bb8-f10678869d8d), [FotMob player stats](https://mobbin.com/screens/80755844-ec6f-4271-985f-3f5661274705), [Premier League league table](https://mobbin.com/screens/d9e1225e-2ec5-4cf3-b418-3af7221409a8), [Premier League commentary](https://mobbin.com/screens/07abca58-4aae-4982-8d13-0466eec4953a), [DAZN live updates](https://mobbin.com/screens/360612f9-7082-4e71-b231-ff78d9a3a063), [Strava home](https://mobbin.com/screens/0d794955-16a5-450d-b10e-dc6df2e9c8bb), [NFL fantasy picks](https://mobbin.com/screens/17752d07-b1d4-4eef-bb99-f38d0e9895e2), [WHOOP widgets](https://mobbin.com/screens/eb710c39-dc18-4cd5-954d-d71b96c42519), [Vapi boards](https://mobbin.com/screens/02a994a5-02e2-4a5d-9d27-8c58f073fb50), [Mintlify search](https://mobbin.com/screens/7c7ad31f-9dfe-4be7-83d7-6002fe31d4d0).

## Lessons

1. **Answer first, evidence second.** Apple Sports, WHOOP and Kraken lead with one statement and put the supporting data underneath. Race Workbench leads with tables. Every redesigned screen should open with its answer row.
2. **One playhead for everything.** Video editors (Descript, VEED) run one cursor through every track. Replay should drive the map, tower, position chart, tyres and events from one lap value.
3. **Deltas need signs as well as colour.** Runna, Fey and Perplexity pair green/red with + / −. Keep that for A/B diffs and "since last forecast".
4. **Probabilities need change, not just level.** Prediction-market rows show "Δ since last update". The app freezes forecasts per session, so "since FP1" is cheap to show and useful.
5. **The cost cap must always be visible** in Fantasy (PL Fantasy, F1 Fantasy). Today it sits in a KPI box below the table.
6. **Typed, filterable event feeds** (Apple Sports key plays, MLS timeline) turn raw track status and pit flags into a story.
7. **Keyboard and command palettes** (Fey, Vapi, Linear) suit the app's power users and cost little in vanilla JS.
8. **Avoid rings and gauges for probabilities** (WHOOP-style). They look good but hide the scale and invite false precision; the existing docs already reject cosmetic confidence gauges.
9. **Spatial metaphors only where space is real.** Pitches and line-ups don't map to F1, but the track map and position river do.
