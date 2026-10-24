# Pace uncertainty and the tuned shadow settings

Two offline candidates following the [multi-score tuning](multi-score-tuning.md)
finding that the engine is overconfident and wants about four times its live
race noise. Neither changes live settings, the run config, the enabled 2026
prospective suite or its pinned source files, frozen forecasts or Discord
delivery.

## 1. `pace_uncertainty_v1` (car-agent engine)

`src/pace_uncertainty.py` treats each car's pace as an estimate, not a fact.
Once per simulated race it draws:

| Term | Size | Source |
| --- | --- | --- |
| Team pace offset, shared by both cars | normal, SD `team_pace_sd` s/lap | estimated from earlier races |
| Driver pace offset | normal, SD `driver_pace_sd` s/lap times the driver's relative `performance_uncertainty` | estimated from earlier races |
| Incident (spin, damage, slow stop, penalty) | 15% chance per driver; lognormal loss, median 6 s, log SD 1.0, capped at 120 s | stated assumption |

The agent engine already adds a small per-driver pace draw (about 0.1 s/lap);
that is kept, so with every new spread at zero the candidate equals
`agent_laps_v1` draw for draw (tested).

### Where the spreads come from

`estimate_pace_error` forecasts each earlier race from the three races before
it, exactly as the benchmark forecasts the target, and splits the misses into
a shared team part and a driver part. The team variance is corrected for the
driver noise in a two-car mean. Each race adds one observation to a prior of
0.5 s/lap (team) and 0.3 s/lap (driver) worth two races, and misses above
3 s/lap are left to the incident term. Only races before the target are used.

On the 2026 packet the estimates settle near **0.48–0.52 s/lap for teams and
0.50–0.52 s/lap for drivers**, against a spread of about 1.1 s/lap in the
forecast gaps themselves. The driver part includes some measurement noise in
a single race's median lap, so it is probably an overestimate; the
half-spread arm checks that.

The incident chance is not fitted. A green-lap timing proxy (laps 3 s or more
over the driver's median, excluding field-wide slow laps) finds such a loss
in about 18% of driver-races, median 4.7 s. It misses the biggest incidents,
which bring yellow flags or a pit stop.

### Limits

- Incident time is added to elapsed time after the race is run, so a car
  that loses 20 s is not then held up in traffic.
- The forecast centre is not shrunk. On this packet the actual relative pace
  regresses on the three-race forecast with a slope of about 0.84, so a
  shrinkage candidate is a natural next test.
- The wrapper lives outside `src/agent_race.py` and `src/simulate.py`
  because the enabled suite pins them. Race Setup and `run_config` cannot
  select it until the post-season source change (same as the challenger).

## 2. `multi_score_tuned_v1` (aggregate engine)

`src/shadow_settings.py` registers the stable tuned settings as named
`parameter_overrides`: `race_pace_seconds_multiplier` 0.52 and
`grid_loss_multiplier` 11.0. Race noise stays at its live 3.8 because its
optimum was still rising at the search limit. Lane: accuracy.

## Results on the 2026 packet (diagnostic)

`python -m scripts.benchmark_pace_uncertainty --output rows.csv`:
`singapore-20261005-v4-venues`, rounds 4–16 (13 inspected races), three
earlier races' pace, actual grid, active track profiles, 1,000 sims, seeds
42/123/777. Lower is better everywhere.

| Arm | Finish MAE | Win Brier | Podium Brier | Top-10 Brier | RPS | Log score | Pair Brier | Teammate Brier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Established | 3.666 | 0.0312 | 0.0732 | 0.1849 | 0.1368 | 3.276 | 0.1932 | 0.2557 |
| multi_score_tuned_v1 | 3.408 | 0.0225 | 0.0794 | 0.1954 | 0.1360 | 3.723 | 0.1940 | 0.2618 |
| tuned + team_noise_v1 | 3.408 | 0.0223 | 0.0786 | 0.1946 | 0.1355 | 3.680 | 0.1929 | 0.2618 |
| agent_laps_v1 | **3.396** | **0.0219** | 0.0734 | 0.1720 | 0.1259 | 3.099 | 0.1784 | 0.2341 |
| pace_uncertainty_v1 | 3.453 | 0.0260 | **0.0696** | 0.1688 | **0.1204** | **2.763** | **0.1708** | 0.2299 |
| pace only (no incidents) | 3.447 | 0.0255 | **0.0696** | **0.1687** | 0.1205 | 2.768 | **0.1708** | **0.2295** |
| incidents only | 3.400 | 0.0222 | 0.0728 | 0.1721 | 0.1256 | 3.068 | 0.1779 | 0.2342 |
| half spreads | 3.405 | 0.0237 | 0.0707 | 0.1710 | 0.1232 | 2.904 | 0.1744 | 0.2319 |

Paired against `agent_laps_v1` (`promotion_check gate`):

| Metric | Mean change | SD across races | Races to detect |
| --- | ---: | ---: | ---: |
| RPS | −0.0055 | 0.0071 | 11 |
| Log score | −0.336 | 0.322 | 6 |
| Pair Brier | −0.0076 | 0.0088 | 9 |
| Podium Brier | −0.0038 | 0.0104 | 46 |
| Finish MAE | +0.057 | 0.106 | worse |
| Win Brier | +0.0040 | 0.0081 | worse |

RPS improved in 9 of 13 races; finish MAE in 3.

### Reading

1. **Uncertain pace is the missing randomness.** Sampling team and driver
   pace improves every whole-distribution score over the agent engine:
   RPS, log score, pair Brier, podium and top-10 Brier. The pace terms do
   almost all of the work; incidents on their own barely move anything.
2. **The cost is the favourite.** Finish MAE and win Brier get slightly
   worse, because a wider field takes win chance away from the strongest
   car. Half spreads keep most of the MAE and win Brier while giving back
   about half of the distribution gain, which suggests the truth is
   in between and that the driver spread is inflated by measurement noise.
3. **The established gate cannot see this.** Against the agent engine the
   candidate fails the gate (loss −1.5%, win Brier regressed), even though
   it is the better probability forecast by every proper score. Against the
   established engine it passes (loss 6.0% better, no Brier regression),
   but that is on inspected races and only a diagnostic.
4. **The tuned settings sharpen without widening.** `multi_score_tuned_v1`
   gets finish order and the win closer to the agent engine, but is
   overconfident: podium, top-10 and log score are worse than live and the
   gate fails on Brier regressions. Team noise at 3 s helps only slightly.
   This matches the tuning: the pace and grid values need the extra
   uncertainty the tuning was asking for, not on their own.

### Suggested next steps

- Use RPS or log score as the primary metric for the 2027 challenger; on
  this evidence a combination of `agent_laps_v1` with `pace_uncertainty_v1`
  is the strongest candidate.
- Test pace shrinkage (slope about 0.84) and spreads between half and full.
- Fit the incident term from timing plus race-control messages before
  relying on it.
- After Abu Dhabi, wire the candidate into `run_config` and Race Setup with
  the other post-season source changes, and register a new suite.
