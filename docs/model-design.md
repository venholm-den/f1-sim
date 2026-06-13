# F1 Simulation Model Design

## Goal

The project should predict race and fantasy outcomes by simulating driver/car performance, not by directly inventing probabilities.

The model should estimate underlying performance values first, then run Monte Carlo simulations. Win chance, podium chance, top 10 chance, expected race points and expected fantasy points should fall out of the simulated results.

## Core Prediction Targets

The model should produce:

* Predicted qualifying/grid strength
* Predicted race pace
* Predicted tyre degradation
* Predicted reliability/DNF risk
* Predicted strategy risk
* Predicted finishing distribution
* Expected race points
* Expected fantasy points
* Fantasy value
* Backtest metrics against real results

## Model Principle

Do not directly calculate:

```text
Driver has 30% podium chance
```

Instead calculate:

```text
Driver has this quali pace, this race pace, this uncertainty, this tyre degradation and this reliability risk
```

Then simulate thousands of races and count how often each outcome happens.

## Main Components

### 1. Data Collection

Inputs:

* FastF1 lap data
* FastF1 session results
* FastF1 weather data
* Track profile data
* Fantasy prices
* Historical race results
* Historical strategy data

Outputs:

* Clean lap details
* Session feature table
* Baseline race feature table

### 2. Qualifying Pace Model

Purpose:

Estimate one-lap speed and expected grid strength.

Inputs:

* Best clean push laps
* CleanPushLap
* Compound
* FreshTyre
* TyreLife
* PitOut / PitIn
* Qualifying results if available
* Sprint qualifying results if available

Outputs:

* quali_pace_score
* quali_confidence
* projected_grid_position

Lower score is better.

### 3. Race Pace Model

Purpose:

Estimate race performance over a stint/race distance.

Inputs:

* Long-run median pace
* Tyre-age adjusted pace
* Compound-adjusted pace
* Historical race pace
* Recent race baseline
* Current practice signal quality

Outputs:

* race_pace_score
* long_run_pace_score
* projected_lap_time
* race_pace_confidence

Lower score is better.

### 4. Tyre Degradation Model

Purpose:

Estimate how much each driver/team loses over a stint.

Inputs:

* TyreLife
* Compound
* Stint
* LapTime
* CleanPushLap
* FreshTyre
* Track temperature
* Historical strategy at the same event

Outputs:

* tyre_deg_score
* degradation_uncertainty
* strategy_risk

### 5. Reliability Model

Purpose:

Estimate DNF and reliability risk.

Inputs:

* Historical DNF rate
* Current season reliability
* Weather
* Track risk
* Red flag / safety car likelihood

Outputs:

* reliability_score
* dnf_probability

### 6. Strategy Model

Purpose:

Estimate pit strategy and risk from tyre availability and degradation.

Inputs:

* Estimated fresh tyres remaining
* Long-run pace
* Compound usage
* Historical race strategy
* Track overtaking difficulty
* Weather

Outputs:

* predicted_strategy
* strategy_score
* old_tyre_risk
* strategy_confidence

### 7. Monte Carlo Race Engine

Purpose:

Run thousands of possible races.

Each simulation should generate:

* Projected total race time per driver
* Finishing order
* DNFs
* Fastest lap
* Driver of the day
* Position changes
* Race points
* Fantasy points

The race engine should not start from probabilities. It should start from performance values.

### 8. Fantasy Scoring

Fantasy points should be calculated inside every simulation.

Each simulation should include:

* Race finish points
* Qualifying points
* Position gain/loss
* Fastest lap
* Driver of the day
* DNF penalty
* Any future constructor or streak rules

Expected fantasy points should be the average of all simulated fantasy scores.

### 9. Backtesting

Every prediction should be saved before the race.

After the race, compare prediction against actual results.

Track these metrics:

* finish_mae
* finish_rmse
* finish_spearman
* top10_brier
* podium_brier
* win_brier
* points_mae
* fantasy_mae

Primary early optimisation metric:

```text
finish_mae + top10_brier
```

Future optimisation metric:

```text
fantasy_mae
```

### 10. Calibration

Backtests should guide parameter changes.

Examples:

* If front-runners are predicted too low, strengthen race baseline and form.
* If practice sessions overreact, reduce current-session weight.
* If too many drivers have 0.00 xPts, increase chaos/variance or improve fantasy category simulation.
* If probabilities are too confident, increase uncertainty.
* If results are too random, reduce chaos and strategy variance.

## Current Development Phases

### Phase 1

Create central performance profile:

* quali_pace_score
* race_pace_score
* long_run_pace_score
* tyre_deg_score
* reliability_score
* strategy_score
* start_score
* performance_uncertainty

### Phase 2

Refactor simulation engine to use projected total race time.

### Phase 3

Expand fantasy scoring to calculate all categories per simulation.

### Phase 4

Build backtest and calibration reports.

### Phase 5

Tune model parameters from real results.
