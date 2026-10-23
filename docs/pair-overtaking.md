# Per-pair pass model (`pair_overtaking_v1`)

The agent engine's established passing rule scales one logistic curve by a
single track factor, `passability = 1 - overtaking_difficulty`. This opt-in
candidate gives each close car pair its own per-lap pass probability instead:

```
logit p = intercept + pace * pace_delta + tyre_age * age_delta
          + compound * softness_delta + track * (difficulty - 0.55)
```

All deltas are the follower's advantage: leader minus follower clean race pace
(s/lap), leader minus follower tyre age (laps), and follower minus leader
compound softness (HARD 0, MEDIUM 1, SOFT 2). `difficulty` is the calibrated
`OvertakingDifficulty` from `data/track_calibration/track_calibration_v1.csv`.

Inspired by the per-pair overtaking model in
F1-StratLab (Apache-2.0); no code was adapted from it.

## Data and fit

The model is fitted only on 2026 races (rounds 1–16 in the
`singapore-20261005-v4-venues` packet). DRS was dropped for 2026, so no DRS
effect is assumed; the electrical aid both cars can use is absorbed into the
coefficients. The fit script refuses packets with earlier seasons.

One observation is an adjacent pair on the same lap number, within 1.0 s at the
line at the start of the lap, with both cars on a green, non-pit lap after the
opening lap. A pass is a reversed crossing order at the end of that lap. Clean
race pace is each driver's median green, non-pit lap time in that race (at
least five laps). This is a timing proxy, not an official overtake count:
passes reversed again before the line are missed.

2,970 pair-laps with 467 passes (15.7% per lap) give:

| Term | Coefficient | Std. error | Reading |
| --- | ---: | ---: | --- |
| intercept | -1.92 | 0.07 | 12.7% per lap for an equal pair at an average track |
| pace (per s/lap) | 1.12 | 0.08 | 1 s/lap faster roughly triples the odds |
| tyre age (per lap) | 0.062 | 0.007 | 10 laps fresher multiplies the odds by 1.9 |
| compound (per step) | 0.01 | 0.07 | No measurable effect once age is known |
| track (per unit difficulty) | -3.15 | 0.42 | Monaco (0.88) vs Monza (0.38): odds about 5x lower |

A pace-by-track interaction was tried and did not improve the rolling score,
so it was left out.

## Backtests

**Pass level.** Each round from 4 to 16 is scored with models fitted on earlier
rounds only (log loss per pair-lap, lower is better, weighted by pair-laps):

| Model | Log loss |
| --- | ---: |
| Constant rate | 0.437 |
| Track factor only (today's single factor) | 0.430 |
| Per-pair model | 0.376 |

The per-pair model is better in 11 of 13 rounds. It is worse at Monaco and
Spain, where the early fits had little hard-track data and over-predicted
passes for cars with large pace gaps.

**Race level.** `python -m scripts.benchmark_pair_overtaking` (actual grid plus three earlier
races' pace, rounds 4–16, 1,000 sims, seeds 42/123/777, 2-second steps). The
pair model is refitted per target race on earlier rounds only. Both agent arms
use calibrated track difficulties.

| Arm | Finish MAE | Win Brier | Podium Brier | Top-10 Brier | Sim passes per race |
| --- | ---: | ---: | ---: | ---: | ---: |
| Established aggregate engine | 3.651 | 0.0308 | 0.0731 | 0.1842 | n/a |
| Agent engine, single factor | 3.396 | 0.0220 | 0.0736 | 0.1719 | 14.9 |
| Agent engine, per-pair model | 3.394 | 0.0221 | 0.0730 | 0.1723 | 19.5 |

At race level the two agent arms are a tie: the pair model has lower finish
MAE in 8 of 13 races but better top-10 Brier in only 3. Both agent arms beat
the aggregate engine on this packet.

Simulated passes per race track the observed close-pair reversals (mean 27 per
race, green laps only) slightly worse with the pair model (correlation 0.53
against 0.67). The clear failure is Monaco: 3 observed reversals, 7 simulated
with the single factor and 21 with the pair model. A linear track term fitted
on mostly mid-difficulty circuits does not shut passing down enough at the
extreme, and Monaco's grid has large pace gaps between neighbours.

**Decision: keep it off.** The pair model predicts individual passes clearly
better, but that does not yet turn into better race forecasts, and it is
miscalibrated at the hardest track. A next step would be a stronger or
non-linear track term (for example a per-circuit intercept shrunk toward the
calibrated difficulty), checked first at Monaco, Hungary and Spain.

## Using it

Local-only, like the other agent candidates. In a run config:

```json
"model": {"race_engine": "agent_laps_v1",
          "agent_settings": {"pair_pass_model": "pair_overtaking_v1"}}
```

The version name loads `data/pair_overtaking/pair_overtaking_v1.json`. A dict
of coefficients is also accepted. The race's track difficulty fills
`track_difficulty` unless the dict sets it. `passability`, `pass_intercept` and
`pass_pace_slope` are ignored while a pair model is set. The offline variant
name is `agent_pair_overtaking_v1` in `src/accuracy_candidates.py`.

Refit (writes new files only):

```powershell
.\.venv\Scripts\python.exe -m scripts.fit_pair_overtaking `
  --output data\pair_overtaking\pair_overtaking_<new>.json `
  --save-pairs data\pair_overtaking\pair_laps_<new>.csv
```

## Limitations

- The engine only rolls for a pass when a follower has been within 1 s for a
  lap and would otherwise make contact. The fitted rate is per close lap,
  whether or not the follower was faster on that lap, so applying it only on
  contact steps is an approximation of the same exposure.
- The calibrated difficulties for the 13 placeholder circuits were themselves
  fitted on archive races that include these 2026 rounds, so the track term is
  not fully out of sample.
- 16 races is a small sample, and every race-level number here is on already
  inspected races. It is a diagnostic, not a promotion test.
