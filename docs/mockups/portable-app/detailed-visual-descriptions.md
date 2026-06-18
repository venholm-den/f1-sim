# Visual Screen Descriptions

This section describes the visual layout, components, cards, charts, tables, and interaction areas that should appear on each screen of the F1 Race Simulator portable app.

---

# 1. Race Setup Screen

## Purpose

The Race Setup screen is the main entry point of the app. It should let the user configure a simulation run quickly, check the selected event context, confirm output settings, and start the simulation.

This screen should feel like a launch panel or control desk.

---

## Overall Layout

The screen should use a dark dashboard layout with red F1-style accents.

The left side should contain the fixed navigation sidebar. The main content area should be split into three sections:

1. A top summary strip.
2. A large simulation parameter panel on the left.
3. Event, weather, output, and run-status panels on the right.

---

## Header Area

At the top of the screen, show:

* Large title: **Race Setup**
* Subtitle: “Configure your race simulation parameters and output preferences.”
* Compact summary cards aligned to the right:

  * Event card
  * Session card
  * Model version card
  * Weather source card

Each summary card should have:

* Small icon
* Uppercase label
* Current value

Example:

```text
EVENT
Monaco Grand Prix

SESSION
Race

MODEL VERSION
v2.4.1

WEATHER SOURCE
Open-Meteo
```

---

## Simulation Parameters Panel

This is the main control panel on the screen.

It should be a large card titled:

```text
Simulation Parameters
Define the core settings for your simulation run.
```

Each parameter should appear as a row with:

* Icon on the left
* Parameter name
* Short description
* Input control on the right

### Visual rows

#### Season

* Calendar icon.
* Dropdown input.
* Example value: `2024`
* Description: “Select the championship season.”

#### Event

* Circuit icon.
* Dropdown input.
* Example value: `Monaco Grand Prix`
* Description: “Select the race event to simulate.”

#### Session

* Flag icon.
* Dropdown input.
* Example value: `Race`
* Description: “Choose the session type to simulate.”

#### Simulation Count

* Dice/cube icon.
* Numeric input with stepper arrows.
* Example value: `1,000`
* Description: “Number of Monte Carlo simulations to run.”

#### Random Seed

* Hash icon.
* Numeric input.
* Example value: `42`
* Description: “Seed for reproducibility. Leave blank for random.”

#### Baseline Races

* Trophy/history icon.
* Numeric input.
* Example value: `50`
* Description: “Number of baseline races used for normalization.”

#### Historical Strategy Lookback

* Trend icon.
* Numeric input with unit suffix.
* Example: `20 races`
* Description: “How many past races to use for strategy modelling.”

#### Default Overtaking Difficulty

* Steering wheel or track-position icon.
* Horizontal slider.
* Values labelled:

  * Easier
  * Balanced
  * Harder
* Current value shown as a percentage, for example `60%`.
* Description: “Baseline difficulty for overtaking in the simulation.”

---

## Track Overview Card

A medium-sized card showing the selected circuit.

Visual elements:

* Mini track map.
* Sector labels:

  * S1
  * S2
  * S3
* Track info table.

Suggested fields:

```text
Circuit: Circuit de Monaco
Length: 3.337 km
Corners: 19
Race Distance: 78 laps
Lap Record: 1:12.909
Tyre Compounds: C5 / C4 / C3
```

Tyre compounds should appear as small circular badges.

---

## Weather Preview Card

This card should show expected race-start weather.

Visual elements:

* Weather icon, such as partly cloudy, rain, or sun.
* Large temperature value.
* Track temperature.
* Rain chance.
* Humidity.
* Wind speed and direction.
* Small hourly timeline.

Example:

```text
Race Start
23°C
Partly Cloudy

Rain Chance: 15%
Humidity: 68%
Wind: 8 km/h NE
Track Temp: 32°C
```

The hourly timeline should show small weather icons and temperatures from race start onward.

---

## Outputs Panel

This card should show what the app will save after the run.

Each row should have:

* Icon
* Toggle switch
* Label
* Short description

Rows:

```text
Save Prediction Snapshot
Save a summary snapshot JSON.

Save Report Images
Save charts and report images.

Save Raw Results
Save full simulation results.

Post to Discord
Post completion summary to Discord.
```

The toggles should be red when enabled and grey when disabled.

If Discord posting is enabled but webhook settings are missing, show a warning state.

---

## Output Directory Panel

A smaller card below the output toggles.

Visual elements:

* Label: **Output Directory**
* Description: “Directory where outputs will be saved.”
* Text input showing path.
* Folder button on the right.

Example:

```text
C:\RaceSimulator\outputs
```

---

## Advanced Options Accordion

A collapsed panel labelled:

```text
Advanced Options
Show advanced configuration options.
```

This should expand to show deeper settings, but should stay collapsed by default.

---

## Run Simulation Button

A large full-width red button.

Text:

```text
▶ Run Simulation
```

It should be visually prominent and placed near the lower-right side of the screen.

---

## Ready-to-Run Status Card

Below the run button, show a status card.

When ready:

```text
Ready to Run
All required parameters are set.
```

Use a green tick icon.

Also show three mini metrics:

```text
Estimated Duration: ~2m 45s
Simulations: 1,000
Estimated Storage: ~320 MB
```

When not ready, show warnings such as:

```text
Missing data source
Missing Discord webhook
Invalid output directory
```

---

## Bottom Help Bar

A full-width information panel at the bottom.

Text:

```text
About this setup
These parameters control how the simulation is executed. Higher simulation counts improve result stability but increase run time. Use a fixed random seed for reproducibility.
```

Include a **Reset to Defaults** button.

---

# 2. Data Sources Screen

## Purpose

The Data Sources screen should let the user see whether all required local files are present, valid, fresh, and correctly loaded.

This screen is mainly for debugging and managing CSV/config inputs.

---

## Overall Layout

The screen should be split into:

1. Header and summary cards.
2. Connected data source cards.
3. Data preview table.
4. Data health panel.
5. Action buttons.

---

## Header Area

Title:

```text
Data Sources
```

Subtitle:

```text
Manage connected data files, configuration paths, and data health.
```

The same top summary cards should remain visible:

* Event
* Session
* Model Version
* Weather Source

---

## Connected Data Sources Panel

A large card titled:

```text
Connected Data Sources
All paths are relative to the configured data directory.
```

Inside, display one card per data source.

---

## Fantasy Prices Card

Visual elements:

* Green money icon.
* Title: **Fantasy Prices**
* File name: `fantasy_prices.csv`
* Full path: `data/fantasy/fantasy_prices.csv`
* Rows loaded count.
* Last updated timestamp.
* Validation status.
* Coverage metric.

Example:

```text
Rows Loaded: 1,024
Last Updated: Today, 14:32
Validation: Valid
Drivers Covered: 20 / 20
```

Use a green tick for valid status.

---

## Track Profiles Card

Visual elements:

* Purple circuit icon.
* Title: **Track Profiles**
* File name: `track_profiles.csv`
* Full path.
* Rows loaded.
* Last updated.
* Validation status.
* Tracks covered.

Example:

```text
Rows Loaded: 103
Validation: Valid
Tracks: 23 / 23
```

---

## FIA Document Index Card

Visual elements:

* Blue document icon.
* Title: **FIA Document Index**
* File name: `fia_index.csv`
* Full path.
* Rows loaded.
* Last updated.
* Validation status.
* Documents indexed count.

This card should support stale warning states.

Example:

```text
Validation: Stale (1 day)
Documents Indexed: 412 files
```

Use amber/yellow for stale data.

---

## Team Power Units Card

Visual elements:

* Yellow engine/power-unit icon.
* Title: **Team Power Units**
* File name: `power_units.csv`
* Full path.
* Rows loaded.
* Last updated.
* Validation status.
* Teams tracked.

Example:

```text
Rows Loaded: 160
Validation: Valid
Power Units Tracked: 8 teams
```

---

## Status Legend

At the bottom of the connected sources panel, show a small legend:

```text
Valid
Stale
Missing
Unknown
```

Each should use a different coloured dot/icon.

Suggested colours:

* Green: valid
* Yellow: stale
* Red: missing
* Grey/blue: unknown

---

## Data Preview Table

A large table showing the currently selected data source.

Example title:

```text
Data Preview: Overtaking Parameters
File: data/params/overtaking_params.csv
```

Show a small badge:

```text
Editable CSV
```

Columns for track profiles:

```text
Track
OvertakingDifficulty
SafetyCarChance
RedFlagBaseChance
Latitude
Longitude
```

Example rows:

```text
Monaco
Imola
Barcelona
Silverstone
Red Bull Ring
```

The table should support:

* Pagination.
* Selected row highlight.
* Horizontal scrolling if needed.
* Button: **Open in Editor**
* Row count display.

Example:

```text
Showing 1 to 5 of 23 rows
```

---

## Data Health Panel

Right-side card titled:

```text
Data Health
Overview of file status and freshness.
```

Show status rows:

```text
All files found: 7
Stale files: 1
Missing files: 0
Unknown status: 0
```

Each row should have:

* Icon
* Label
* Count

---

## Last Validation Panel

Small card showing:

```text
Last Validation
Today, 14:32:18
```

Button:

```text
View Log
```

---

## Actions Panel

Right-side action card titled:

```text
Actions
Run data operations and validations.
```

Buttons:

```text
Reload Data
Validate All
Open Data Folder
```

The **Reload Data** button should be the primary red action.

---

## Data Directory Panel

Small card showing the root data directory.

Visual elements:

* Path input.
* Folder button.
* Link to Settings.

Example:

```text
C:\RaceSimulator\data
```

Text:

```text
Change directory in Settings
```

---

## Auto-Reload Toggle

At the bottom-right of the screen, include:

```text
Auto-reload on file change
```

Toggle should be green when enabled.

---

# 3. Model Signals Screen

## Purpose

The Model Signals screen should explain how the simulation blends baseline knowledge with current session data.

It should make the model feel understandable and adjustable.

---

## Overall Layout

The screen should use a dashboard layout with:

1. Weighting panels at the top.
2. Signal quality and uncertainty cards in the middle.
3. Charts at the bottom.
4. Model explainability panel on the right.

---

## Header Area

Title:

```text
Model Signals
```

Subtitle:

```text
Configure how the model blends baseline knowledge with current session data.
```

Top summary cards remain:

* Event
* Session
* Model Version
* Weather Source

---

## Current Session Weights Panel

Card title:

```text
CURRENT_SESSION_WEIGHTS
```

Subtitle:

```text
Live weights used for this session's forecast.
```

Visual:

Horizontal bars for:

```text
Practice
Qualifying
Race this session
```

Each bar should show:

* Label
* Filled bar
* Percentage value

Example:

```text
Practice: 18%
Qualifying: 42%
Race this session: 40%
Total: 100%
```

The active/important signals should use red bars. Less important signals can use grey.

---

## Session Weights Panel

Card title:

```text
SESSION_WEIGHTS
```

Subtitle:

```text
Adjust the target impact of each session type.
```

Controls:

* Practice Target slider
* Qualifying Target slider
* Race Target slider

Each slider should have:

* Red fill
* Numeric percentage box on the right

Example:

```text
Practice Target: 20%
Qualifying Target: 40%
Race Target: 40%
```

Text note:

```text
Weights are automatically normalized to sum to 100%.
```

---

## Baseline Race Decay Card

Small card showing:

```text
Baseline Race Decay
How quickly baseline knowledge decays as new data arrives.
```

Visual:

* Slider.
* Numeric value.
* Help text.

Example:

```text
0.18
Lower = slower decay, trust baseline longer.
Higher = faster decay, trust new data more.
```

---

## Current Signal Quality Card

Circular gauge showing signal quality.

Example:

```text
0.82
High
```

Visual details:

* Green circular progress ring.
* Central value.
* Label beneath value.
* Short explanation.

Text:

```text
Signal quality reflects consistency, volume, and recency of the data.
```

---

## Practice Pace Cap Card

Small card showing:

```text
Practice Pace Cap
Maximum influence practice data can have on the forecast.
```

Visual:

* Slider.
* Percentage box.
* Example value: `25%`.

Help text:

```text
Caps the impact of practice to prevent over-weighting unrepresentative data.
```

---

## Qualifying Pace Cap Card

Small card showing:

```text
Qualifying Pace Cap
Maximum influence qualifying data can have on the forecast.
```

Visual:

* Slider.
* Percentage box.
* Example value: `60%`.

Help text:

```text
Helps balance one-lap pace versus race pace relevance.
```

---

## Model Uncertainty Card

Circular gauge showing model uncertainty.

Example:

```text
0.26
Medium
```

Visual details:

* Orange circular gauge.
* Lower value should be better.
* Label: Low / Medium / High.

Text:

```text
Lower is better. Reflects spread in outcomes and input confidence.
```

---

## Baseline vs Current-Session Influence Chart

A wide card showing a stacked horizontal bar.

Example:

```text
Baseline pre-event knowledge: 33%
Current session live data: 67%
```

Visual:

* Grey section for baseline.
* Red section for current session.
* Text below explaining how the forecast is being weighted.

---

## Signal Confidence Over Recent Sessions Chart

Line chart showing confidence trend.

X-axis:

```text
P1
P2
P3
Q1
Q2
Q3
Race
```

Y-axis:

```text
Signal Quality
0.00 to 1.00
```

Line should show the current model’s confidence improving or dropping over sessions.

---

## Input Signal Distribution Radar Chart

Radar/spider chart showing relative strength of input categories.

Categories:

```text
Qualifying
Race
Strategy
Reliability
```

Optional extra categories:

```text
Weather
Track Evolution
Tyre Deg
```

Each axis should be scored from 0 to 1.

The chart should show the model’s current reliance pattern.

---

## Model Explainability Panel

Right-side tall panel titled:

```text
Model Explainability
Why the model is predicting what it is.
```

### Top Drivers of Current Forecast

Horizontal bar chart showing input contribution:

```text
Qualifying pace: 34%
Race long-run pace: 28%
Tyre degradation: 17%
Track evolution: 10%
Practice consistency: 6%
Weather stability: 5%
```

Use red bars for high-impact signals and grey bars for low-impact signals.

---

## Key Active Inputs List

List with icons and impact labels:

```text
Recent qualifying laps (Q3) — High impact
Race stint data (laps 10–40) — High impact
Medium tyre degradation model — Medium impact
Fuel load normalization — High impact
Track evolution model — Medium impact
Weather forecast stable — Low impact
```

Use:

* Green for high confidence/high impact.
* Orange for medium impact.
* Grey for low impact.

---

## Model Notes Panel

Text area at the bottom of the explainability panel.

Example:

```text
Low uncertainty with strong qualifying and race pace signals.
Monitor tyre degradation if track temperature rises above expected levels.
```

---

## Bottom Help Bar

Information strip:

```text
About Model Signals
Model Signals control how the simulator blends baseline knowledge with live session data. Adjust weights and caps to match your confidence in the available data and the characteristics of the circuit and conditions.
```

Button:

```text
Reset to Defaults
```

---

# 4. Weather & Reliability Screen

## Purpose

This screen should show how weather, race-control context, chaos, degradation, and reliability risks affect the simulation.

It combines environmental inputs with risk outputs.

---

## Overall Layout

The screen should contain:

1. Chaos modifier cards at the top.
2. Weather forecast and race-control context in the middle.
3. Reliability projections table at the bottom.
4. Race risk summary cards on the right.

---

## Header Area

Title:

```text
Weather & Reliability
```

Subtitle:

```text
Manage environmental conditions, race control factors and reliability projections.
```

Top summary cards:

* Event
* Session
* Model Version
* Weather Source

---

## Race Control & Chaos Modifiers Panel

A wide panel containing five modifier cards.

Each card should include:

* Icon
* Parameter name
* Numeric value
* Slider
* Short explanation
* Risk label

---

## Chaos Factor Card

Label:

```text
chaos_factor
```

Visual:

* Red lightning icon.
* Numeric value, for example `0.68`.
* Red slider.
* Risk label: High.

Text:

```text
Overall disruption potential from incidents, safety cars, flags and events.
```

---

## Strategy Factor Card

Label:

```text
strategy_factor
```

Visual:

* Purple strategy/pit icon.
* Numeric value, for example `0.54`.
* Purple slider.
* Risk label: Medium.

Text:

```text
How likely strategy variance will affect finishing order.
```

---

## DNF Factor Card

Label:

```text
dnf_factor
```

Visual:

* Orange warning icon.
* Numeric value, for example `0.72`.
* Red/orange slider.
* Risk label: High.

Text:

```text
Increased probability of DNF due to chaos and incidents.
```

---

## Degradation Factor Card

Label:

```text
degradation_factor
```

Visual:

* Yellow gear/tyre icon.
* Numeric value, for example `0.61`.
* Yellow slider.
* Risk label: Medium.

Text:

```text
Expected impact of tyre and car degradation over race distance.
```

---

## Uncertainty Factor Card

Label:

```text
uncertainty_factor
```

Visual:

* Blue question mark icon.
* Numeric value, for example `0.58`.
* Blue slider.
* Risk label: Medium.

Text:

```text
Forecast and model uncertainty impact on outcome confidence.
```

---

## Weather Forecast Card

A large weather card showing current and forecast conditions.

Visual elements:

* Weather icon.
* Track temperature.
* Rain chance.
* Humidity.
* Wind speed/direction.
* Air temperature.
* Hourly forecast row.

Example fields:

```text
Track Temp: 23°C
Rain Chance: 65%
Humidity: 78%
Wind: 8 km/h NE
Air Temp: 20°C
```

Hourly timeline:

```text
14:00  23°C  60%
15:00  23°C  65%
16:00  24°C  70%
17:00  24°C  65%
18:00  23°C  55%
19:00  23°C  45%
20:00  22°C  35%
```

Each hour should have:

* Weather icon
* Temperature
* Rain chance
* Coloured underline showing risk intensity

---

## Race Control Context Card

Card title:

```text
Race Control Context
```

This should show recent messages or inferred race-control signals.

Example rows:

```text
12:45 Light rain reported in sectors 1 & 2 → chaos_factor up
12:15 Track limits enforcement increased → strategy_factor up
11:50 Multiple incidents in support races → chaos_factor up
11:10 Pirelli: High graining expected → degradation_factor up
10:40 Track evolution slower than normal → uncertainty_factor stable
```

Each row should show:

* Timestamp
* Message
* Impact indicator
* Coloured arrow

At the bottom:

```text
+ 2 older messages
View all
```

---

## Reliability Projections Table

A wide table at the bottom.

Columns:

```text
Position
Team
Base DNF %
Team Mechanical DNF %
Power-Unit DNF %
Reliability Score
Effective DNF Probability %
Risk Level
```

The reliability score should show both a number and a mini bar.

Example:

```text
Red Force Racing
Base DNF: 6.2%
Team Mech DNF: 3.1%
PU DNF: 2.4%
Reliability Score: 86/100
Effective DNF Prob: 9.8%
Risk: Medium
```

Risk level should use coloured dots:

* Green: Low
* Yellow: Medium
* Red: High
* Dark red: Very High

---

## Race Risk Outlook Panel

Right-side vertical panel with large risk cards.

### Safety Car Probability

Visual:

* Safety car icon.
* Large percentage.
* Risk badge.

Example:

```text
Safety Car Probability
64%
High
Track position swings likely.
```

---

### Red Flag Probability

Visual:

* Red flag icon.
* Large percentage.
* Risk badge.

Example:

```text
Red Flag Probability
18%
Medium
Session stoppage possible.
```

---

### Wet Race Risk

Visual:

* Water droplet icon.
* Large percentage.

Example:

```text
Wet Race Risk
72%
High
Rain likely to impact strategy.
```

---

### High Degradation Risk

Visual:

* Tyre icon.
* Large percentage.

Example:

```text
High Degradation Risk
58%
Medium
Tyre wear above normal range.
```

---

## Overall Risk Level Card

Large visual badge:

```text
Overall Risk Level
HIGH
```

Supporting text:

```text
Race highly volatile. Expect disruptions.
```

The badge should use a red background.

---

## Model Confidence Card

Circular confidence gauge.

Example:

```text
78%
High Confidence
Stable conditions with moderate uncertainty.
```

Use a green circular gauge.

---

## Risk Level Guide

Small legend explaining the risk levels.

Example:

```text
Low
Medium: 8% - 12%
High
Very High: > 18%
```

---

# 5. Results & Strategy Screen

## Purpose

The Results & Strategy screen should show the final simulation output after a run.

It should be the most polished and shareable screen in the app.

---

## Overall Layout

The screen should include:

1. Simulation summary cards at the top.
2. Scenario tabs below.
3. Probability charts and finish distribution.
4. Strategy recommendations.
5. Fantasy projections.
6. Insights panel.
7. Export buttons at the bottom.

---

## Header Area

Title:

```text
Results & Strategy
```

Subtitle:

```text
Post-simulation results, insights, and strategy recommendations.
```

Top summary cards:

* Event
* Session
* Model Version
* Weather Source

---

## Simulation Summary Cards

Top row of metric cards.

### Runs Card

Shows total simulations completed.

Visual:

* Dice/cube icon.
* Large number.
* Small sparkline or distribution bars.

Example:

```text
Runs
1,000
Simulations
```

---

### Runtime Card

Shows how long the simulation took.

Visual:

* Clock icon.
* Runtime value.
* Small sparkline.

Example:

```text
Runtime
2m 45s
Total time
```

---

### Confidence Card

Shows model confidence.

Visual:

* Shield icon.
* Large percentage.
* Green confidence bar.

Example:

```text
Confidence
92%
High
```

---

### Safety Car Probability Card

Visual:

* Safety car icon.
* Large percentage.
* Change versus baseline.
* Yellow sparkline.

Example:

```text
Safety Car Prob.
28%
+4% vs baseline
```

---

### Red Flag Probability Card

Visual:

* Red flag icon.
* Large percentage.
* Change versus baseline.
* Red sparkline.

Example:

```text
Red Flag Prob.
6%
+1% vs baseline
```

---

## Scenario Tabs

Below the summary cards, show scenario selector tabs.

Example:

```text
Scenario A: Base Forecast
Scenario B: Dry, Low SC
Scenario C: Wet Risk
+ Add Scenario
```

The active scenario should be highlighted with a red border.

This allows the user to compare different model assumptions.

---

## Win & Podium Probability Chart

Left-side chart.

Card title:

```text
Win & Podium Probability
```

Visual:

* Horizontal bar chart.
* Driver ranking.
* Team logo/icon or colour marker.
* Red bar for win probability.
* Grey bar for podium probability.
* Dropdown filter, e.g. `Top 10 Drivers`.

Example rows:

```text
Verstappen
Win: 36.2%
Podium: 62.8%

Leclerc
Win: 22.4%
Podium: 52.1%

Norris
Win: 15.3%
Podium: 42.7%
```

Include a note:

```text
Probabilities may not sum to 100% due to rounding.
```

---

## Finish Distribution Heatmap

Centre chart.

Card title:

```text
Finish Distribution (Top 10)
```

Visual:

* Heatmap grid.
* Drivers on rows.
* Finishing positions on columns.
* Cell values as percentages.
* Colour intensity showing likelihood.

Columns:

```text
1
2
3
4
5
6
7
8
9
10
```

Rows:

```text
VER
LEC
NOR
HAM
RUS
SAI
ALO
GAS
HUL
ALB
```

Add a colour legend:

```text
Higher %
Lower %
```

The most likely finishing cells should use stronger warm colours.

---

## Strategy Recommendation Panel

Right-side card.

Card title:

```text
Strategy Recommendation
```

Columns:

```text
Rank
Strategy
Win %
Podium %
Average Points
Reliability Risk
```

Each strategy should be shown as a row with tyre compound badges.

Example:

```text
1. Medium → Hard
Win: 34.2%
Podium: 60.1%
Avg Points: 18.7
Reliability Risk: Low

2. Hard → Medium
Win: 30.1%
Podium: 55.7%
Avg Points: 17.2
Reliability Risk: Low

3. Soft → Hard → Medium
Win: 28.3%
Podium: 53.0%
Avg Points: 16.3
Reliability Risk: Medium
```

Tyre badges should use:

* Red for Soft
* Yellow for Medium
* White/grey for Hard

At the bottom:

```text
Strategy results are based on current model assumptions.
```

---

## Fantasy Projections Table

Bottom-left large table.

Card title:

```text
Fantasy Projections
```

Columns:

```text
Driver
Team
Average Points
Ceiling
Floor
Price
xPPM
Value Tier
```

Example rows:

```text
Verstappen
Red Bull
Avg: 18.7
Ceiling: 34.2
Floor: 8.1
Price: $27.3m
xPPM: 0.685
Value Tier: Elite
```

Value tier should use coloured pills:

* Purple: Elite
* Blue: High
* Green/teal: Mid
* Grey: Low

There should be star icons beside top recommended fantasy picks.

---

## Insights Panel

Bottom-right card.

Card title:

```text
Insights
```

This should show short model-generated summary points.

Example:

```text
Verstappen has the highest win probability by a clear margin.

Medium → Hard offers the best balance of upside and risk.

Safety Car probability is elevated, flexible strategies are favoured.

Top 3 drivers offer the best fantasy value by xPPM.
```

Each insight should have a small icon.

---

## Bottom Action Bar

At the bottom of the screen, show action buttons:

```text
Reset to Defaults
Export CSV
Save Snapshot
Generate Images
Post to Discord
```

The Discord button should include the Discord icon.

If Discord is unavailable, the button should be disabled or show a warning tooltip.

---

# 6. Tyre Strategy Screen

## Purpose

The Tyre Strategy screen should let the user understand tyre allocation, degradation assumptions, inventory risk, and candidate strategy ranking.

This screen should focus on how strategy choices change race outcomes.

---

## Main Visuals

### Tyre Inventory Cards

Show one card per compound:

```text
Soft
Medium
Hard
Intermediate
Wet
```

Each card should include:

* Compound badge.
* New sets count.
* Scrubbed sets count.
* Used sets count.
* Unknown sets count.

Example:

```text
Soft
New: 1
Scrubbed: 1
Used: 2
Unknown: 0
```

---

### Tyre Status Visual

A simple top-down car diagram with four tyres.

Each tyre should show:

* Current wear estimate.
* Compound colour.
* Status badge.

Example:

```text
FL: Medium, 82%
FR: Medium, 84%
RL: Medium, 79%
RR: Medium, 80%
```

---

### Degradation Source Card

Shows what source the app is using for degradation.

Possible values:

```text
Driver long-run
Team long-run
Field long-run
Weather-adjusted default
```

Visual:

* Source label.
* Confidence badge.
* Expected degradation per lap.

Example:

```text
Source: Team long-run
Confidence: Medium
Estimated degradation: 0.084s/lap
```

---

### Candidate Strategy Table

Main table comparing strategy options.

Columns:

```text
Rank
Strategy
Expected Race Time
Win Probability
Podium Probability
Tyre Risk
Track Position Risk
Inventory Risk
Overall Score
```

Example strategies:

```text
Medium → Hard
Hard → Medium
Soft → Hard
Soft → Medium → Hard
Medium → Hard → Medium
```

---

### Strategy Timeline Visual

Horizontal timeline showing stint length.

Example:

```text
Lap 1 ─ Medium ─ Lap 28 ─ Hard ─ Finish
```

Each compound should be colour-coded.

---

### Overtaking Difficulty Impact Card

Shows how the track changes strategy preference.

Example:

```text
Overtaking Difficulty: Very High
Track Position Preservation: Strongly favoured
Recovery Strategy Value: Low
```

Use a slider or gauge.

---

### Inventory Risk Meter

Circular or horizontal gauge.

Example:

```text
Inventory Risk
Medium
Unknown dry sets increase uncertainty.
```

---

# 7. Fantasy Screen

## Purpose

The Fantasy screen should show how the simulation converts race and qualifying predictions into fantasy points and value.

It should support both viewing projections and editing scoring rules.

---

## Main Visuals

### Fantasy Projection Leaderboard

A ranked table.

Columns:

```text
Rank
Driver
Team
Average Points
Ceiling
Floor
Price
xPPM
Value Rank
Risk
```

Use:

* Stars for top picks.
* Value tier pills.
* Team colour markers.
* Risk badges.

---

### Value Scatter Plot

Chart showing:

* X-axis: Price
* Y-axis: Projected points
* Bubble size: Ceiling
* Colour: Value tier

This should quickly reveal underpriced drivers.

---

### Points Breakdown Card

When a driver is selected, show where their points come from:

```text
Finish points
Qualifying points
Position gain/loss
Fastest lap chance
DOTD chance
DNF penalty risk
```

Use a stacked bar chart.

---

### Scoring Rules Editor

Editable section for:

```text
Finish points
Qualifying points
Position gain points
Position loss points
Position change caps
Fastest lap bonus
Driver of the day bonus
DNF penalty
```

This should be presented as a table rather than raw JSON.

---

### Fantasy Filters

Filter controls:

```text
Show value picks only
Hide drivers above price cap
Include qualifying points
Include fastest lap bonus
Include DOTD bonus
Show high-risk picks
```

---

# 8. Compare Screen

## Purpose

The Compare screen should let the user compare multiple simulation scenarios side-by-side.

This is useful for dry versus wet race, high safety-car risk, red-flag scenario, and different strategy assumptions.

---

## Main Visuals

### Scenario Cards

At the top, show cards for each scenario:

```text
Scenario A: Base Forecast
Scenario B: Dry Race
Scenario C: Wet Risk
Scenario D: High Safety Car
```

Each card should show:

* Key modified assumptions.
* Run count.
* Confidence.
* Risk level.
* Last run time.

---

### Scenario Comparison Table

Main table.

Columns:

```text
Driver
Base Win %
Wet Win %
High SC Win %
Red Flag Win %
Base Podium %
Wet Podium %
High SC Podium %
```

Rows are drivers.

Cells should use conditional formatting.

---

### Delta Chart

Bar chart showing how probabilities changed from the base scenario.

Example:

```text
Driver
Norris: +4.2% in wet scenario
Verstappen: -2.1% in wet scenario
Leclerc: +1.8% in red-flag scenario
```

---

### Strategy Comparison Matrix

Grid comparing best strategies by scenario.

Example:

```text
Base Forecast: Medium → Hard
Wet Risk: Intermediate → Medium
High Safety Car: Hard → Medium
Red Flag: Soft → Hard
```

---

### Scenario Insight Panel

Short generated explanation:

```text
Wet conditions increase variance and improve outcomes for drivers with stronger long-run pace.

High safety-car probability favours one-stop flexibility.

Red-flag compression reduces the penalty for poor starting position.
```

---

# 9. Settings Screen

## Purpose

The Settings screen should handle app configuration, local folders, data paths, Discord settings, theme options, and reset actions.

---

## Main Visuals

### App Settings Card

Fields:

```text
Default season
Default simulation count
Default output directory
Default data directory
Auto-reload data files
Open output folder after run
```

---

### Data Path Settings Card

Configurable paths:

```text
Fantasy prices path
Track profiles path
FIA document index path
Team power units path
Snapshots folder
Reports folder
Logs folder
```

Each row should have:

* Path field.
* Folder/file picker button.
* Validation status.

---

### Discord Settings Card

Fields:

```text
Discord posting enabled
Webhook URL
Error webhook URL
Test message button
Mask webhook in logs
```

Webhook fields should be masked.

If a webhook is missing:

```text
Discord not configured
Posting is disabled until a webhook URL is provided.
```

---

### Theme Settings Card

Controls:

```text
Theme: Dark / Light / System
Accent colour
Compact mode
Show advanced controls by default
```

Dark mode should be the default.

---

### Packaging / Security Info Card

Show local app information:

```text
App version
Model version
Python/runtime version
Build type
Portable directory
Config file location
```

Include a note about Windows SmartScreen if the app is unsigned.

---

### Reset / Maintenance Card

Buttons:

```text
Reset App Settings
Clear Cache
Clear Logs
Restore Default Config
Open Logs Folder
Open App Folder
```

Dangerous actions should use warning colours and confirmation prompts.

---

# 10. Backtesting Screen

## Purpose

The Backtesting screen should compare previous prediction snapshots against actual race results.

This is useful for improving the model over time.

---

## Main Visuals

### Snapshot List

Table of saved prediction snapshots.

Columns:

```text
Date
Season
Event
Session
Model Version
Simulation Count
Status
```

Status examples:

```text
Pending result
Matched
Missing actual result
Backtested
```

---

### Prediction vs Actual Table

Columns:

```text
Driver
Predicted Average Finish
Actual Finish
Prediction Error
Predicted Win %
Predicted Podium %
Actual Result
```

Use conditional formatting to highlight accurate and inaccurate predictions.

---

### Model Accuracy Cards

Summary cards:

```text
Mean Absolute Error
Winner Prediction Accuracy
Podium Prediction Accuracy
Top 10 Accuracy
DNF Accuracy
Fantasy Points Error
```

---

### Calibration Chart

Chart comparing predicted probabilities against actual outcomes.

Example:

```text
Predicted 20% win chance drivers should win around 20% of the time over many races.
```

---

### Backtesting Insights Panel

Generated summary:

```text
The model is overconfident on high qualifying performance at street circuits.

DNF probabilities are slightly under-estimated in wet races.

Fantasy value predictions are strongest for midfield drivers.
```

---

# Shared Visual Design Rules

## Navigation Sidebar

Every screen should use the same sidebar.

Items:

```text
Race Setup
Data Sources
Model Signals
Weather & Chaos
Reliability
Tyre Strategy
Fantasy
Results
Compare
Settings
```

The active item should be highlighted with:

* Red background gradient.
* Red left border.
* White text.
* Matching icon.

Inactive items should be grey with subtle hover states.

---

## Top Summary Cards

Most screens should keep the same top summary cards:

```text
Event
Session
Model Version
Weather Source
```

These make the app feel consistent and remind the user what scenario they are editing.

---

## Card Style

Cards should use:

* Dark charcoal background.
* Thin grey border.
* Slight inner glow or soft shadow.
* Rounded corners.
* Compact uppercase section titles.
* Small muted helper text.
* Red highlights for primary simulation controls.
* Green/yellow/red states for health and risk.

---

## Chart Style

Charts should use:

* Dark backgrounds.
* Thin gridlines.
* Clear axis labels.
* Red for primary prediction values.
* Grey for comparison/baseline values.
* Yellow/orange for risk and degradation.
* Green for valid/healthy/confident states.
* Blue for weather/uncertainty.

---

## Status Colours

Recommended status palette:

```text
Red: primary action, risk, win probability
Green: valid, ready, confidence, low risk
Yellow: medium risk, stale files, degradation warning
Orange: high uncertainty, caution
Blue: weather, information, uncertainty
Grey: disabled, baseline, inactive
```

---

## Interaction Details

Each editable parameter should have:

* Label.
* Short description.
* Current value.
* Tooltip explaining what it changes.
* Reset-to-default option where relevant.
* Warning if the value is outside a normal range.

Advanced settings should be hidden behind accordions or an “Advanced Mode” toggle.

---

## Empty States

The app should include clear empty states.

Examples:

```text
No simulation has been run yet.
Configure race setup and press Run Simulation.

No FIA documents found.
Reload data or check the FIA document index path.

No fantasy prices loaded.
Select a valid fantasy prices CSV.
```

---

## Error States

Errors should appear as readable cards, not raw stack traces.

Example:

```text
Simulation failed
Reason: Missing fantasy_prices.csv

Suggested fix:
Check the configured data directory or reload data sources.
```

There should also be:

```text
View Log
Open Logs Folder
Copy Error
```

---

## Loading States

When running a simulation, show:

* Progress indicator.
* Current step.
* Elapsed time.
* Estimated remaining time.
* Cancel button, if supported.

Example steps:

```text
Loading FastF1 session data
Validating local CSV files
Building driver features
Applying weather modifiers
Running Monte Carlo simulations
Generating report images
Saving outputs
Posting to Discord
```

---

## Success State

After a successful run, show:

```text
Simulation completed
1,000 runs completed in 2m 45s
Outputs saved to C:\RaceSimulator\outputs
```

Include buttons:

```text
View Results
Open Output Folder
Post to Discord
```
