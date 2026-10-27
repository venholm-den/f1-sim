# Grid-slot retirements, Driver of the Day and the Rhter Mexico comparison, 27 October 2026

Kyle compared our Mexico City 2026 forecast with Rhter Sim's early preset
(dry, average conditions). Rhter's numbers are a reference, not the truth.
Three gaps stood out, and this change addresses each one.

## What was different

| | Ours (before: 5 races, lap-quality retirements) | Rhter |
| --- | --- | --- |
| Retirement chance | 2.9–4.2% for every driver | 8% at the front, 10–14% midfield, 18–53% at the back |
| Order by average finish | VER, LEC, ANT, PIA, HAD, HAM, NOR, LAW, RUS | ANT, LEC, VER, HAM, RUS, NOR, PIA, HAD, LAW |
| Driver of the Day | HAD 17%, LAW 11%, VER 1.5% | LEC 22%, VER 21%, HAM 17%, ANT 15% |

## 1. Retirements by grid slot (`season_grid_dnf_v1`, experimental)

Across 2024–2026 race classifications, cars starting in the top six retired
about 5–6% of the time, P7–P18 about 14%, and P19–P22 about 27%. The pattern
holds in 2024 and 2025 too, when reliability was spread evenly between teams.
`season_dnf_v1` ignores it, so in those seasons it gives every driver the field
rate (12–15%), which is too high at the front and too low at the back.

`apply_season_grid_retirement_risk` in `src/retirement_season.py`:

- fits a logistic slope of retirement on grid slot from the two earlier
  seasons in the retirement history, with a declared prior of 1.5 log-odds from
  pole to last (sd 0.75) and a fallback to the prior below 100 entries;
- compares this season's team and driver retirements with what their own grid
  slots predict (observed over expected), shrunk with the same data-driven
  strength as `season_dnf_v1`;
- applies the result at this race's grid slot (estimated grid before
  qualifying, the real grid after it).

The slope is fitted on earlier seasons only, because within a season it is
confounded with which teams break down. Pit-lane starts count as last.

## 2. Longer pace history

`n_baseline_races` stays a user setting. Ten races (one predeclared
alternative to the default five, not a search) was compared on the same
replays. The existing age weighting (1 / (1 + 0.45 × age)) still favours
recent races.

## Backtest

`scripts.benchmark_retirement_models` now includes the new arm. It ran from
the historical library for 2021–2026 at 2,000 simulations and seeds 42/123,
once with five and once with ten races of pace history. Rows are paired
against the live settings (five races, established retirements). 2025–2026
were already inspected, so this is diagnostic evidence, not fresh races.

| Candidate | Stage | Split | Races | RPS gain | Finish MAE change (95% race bootstrap) |
| --- | --- | --- | ---: | ---: | --- |
| Grid-slot retirements, 10 races | PRE | 2021–24 | 56 | **6.9%** | −0.153 [−0.224, −0.082] |
| | PRE | 2025–26 | 34 | **5.1%** | −0.093 [−0.198, +0.010] |
| | FP2 | 2021–24 | 58 | **6.1%** | −0.075 [−0.142, −0.009] |
| | FP2 | 2025–26 | 28 | **5.2%** | −0.067 [−0.178, +0.039] |
| | Q | 2021–24 | 71 | **7.7%** | −0.135 [−0.198, −0.073] |
| | Q | 2025–26 | 37 | **10.0%** | −0.175 [−0.264, −0.087] |
| Grid-slot retirements, 5 races | PRE / FP2 / Q | 2025–26 | 34 / 28 / 37 | 3.0% / 2.6% / 6.5% | −0.030 / +0.007 / −0.074 |
| Established retirements, 10 races | PRE / FP2 / Q | 2025–26 | 34 / 28 / 37 | 3.1% / 3.5% / 4.7% | −0.098 / −0.114 / −0.128 |
| `season_dnf_v1`, 5 races | PRE / FP2 / Q | 2025–26 | 34 / 28 / 37 | 2.8% / 3.1% / 4.9% | worse at PRE and Q |

The combination clears the 5% paired-RPS bar at every stage in both splits,
and win, podium, top-10 and retirement Brier all improve. The one gate it
still fails is the Q rule "beat qualifying order": 3.43 finish MAE against
3.31 for the plain grid on 2025–26 (3.43 against 3.43 on 2021–24). Every
candidate so far fails that rule.

On 27 October Kyle chose to make both the default: `retirement_model`
`season_grid_dnf_v1` and `n_baseline_races` 10 (code defaults and
`config/default_run_config.json`). The earlier rule stays selectable as
"Earlier rule (lap quality)". This is a promotion on inspected replays, not
on six fresh races. The protected scheduled runtime keeps its sealed source
until a new runtime is prepared, so Discord forecasts and the four-arm suite
do not change with this merge. A saved app setting for baseline races is kept
as the user set it.

## 3. Driver of the Day

The simulator chose Driver of the Day with a hand-set rule that favoured big
position gains. In the f1fantasytools archive (2024–2026, one vote winner per
race) the race winner took 41% of votes, P2–P3 17% each, P4–P5 3%, P6–P10 3%
and P11+ under 1%. The old rule scored 3.21 log loss per race on 2026, worse
than picking a finisher at random (3.00).

`DOTD_LOGIT` in `src/model_config.py` replaces it with a conditional logit
fitted on 48 races from 2024–2025: finishing bands plus places gained inside
the top ten. On the 18 held-out 2026 races it scores 1.47. Only fantasy
outputs change: the draw is the last random draw in a simulation, so finishing
positions, retirements and race scores stay the same for a given seed. 2023
is left out because its fantasy round numbers do not line up with the race
archive.

## Mexico after the change

PRE forecast from the 18 earlier 2026 races, 4,000 simulations, seed 42.
Compared with Rhter across 22 drivers:

| Measure | Live | Grid-slot retirements, 10 races, new DOTD |
| --- | --- | --- |
| xPts mean absolute gap | 6.2 | 4.0 |
| xPts rank correlation | 0.71 | 0.90 |
| DNF % mean absolute gap | 12.5 | 3.8 |
| DNF % rank correlation | 0.37 | 0.89 |
| Fastest lap % mean absolute gap | 2.7 | 1.4 |
| DOTD % rank correlation | 0.20 | 0.86 |

New retirement chances: ANT 10%, VER 12%, LEC 12%, STR 44%, BOT 40%,
ALO 30%, PER 30%, ALB 30%. Order: ANT, VER, LEC, NOR, HAM, HAD, PIA, LAW, RUS.

Remaining gap: Rhter rates Hamilton, Russell and Leclerc higher (xPts 25, 24,
29 against our 17, 12, 21). That comes from pace, and nothing here forces our
pace towards Rhter's.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -c "from scripts.benchmark_retirement_models import run; run(r'$env:LOCALAPPDATA\RaceWorkbench', 'outputs/retirement_review/NEW/h10', n_sims=2000, seeds=(42, 123), history=10)"
```

Repeat with `history=5`, then pair `race_metrics.csv` rows on year, round and
session against the `established` arm of the five-race run.
