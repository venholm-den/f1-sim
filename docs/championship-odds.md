# Championship odds

The **Championship** page (Analyse group) estimates the drivers' and
constructors' titles by simulating every remaining race and sprint of a season
from the current standings. It is independent of saved race runs and of the
per-race simulator, and it changes no forecast, model or frozen file.

## Inputs

- **Completed classifications** come from the local Historical data library
  (`data/historical_library/<year>/detailed/*_R|*_S`, then results-only Jolpica
  rounds). A finished session that is not archived is fetched with FastF1. If
  that also fails, the page warns that its points are missing from the
  standings. A session that started under two days ago and has no results is
  treated as still outstanding.
- **Remaining sessions** come from the FastF1 event schedule (`Race` and
  `Sprint` sessions not yet counted). Points use the current tables: 25–1 for
  the top ten in a race and 8–1 for the top eight in a sprint, with no fastest
  lap point.
- The **current roster** is the latest race's entry list, with each driver's
  current team. Constructors keep every point their cars have scored, whoever
  drove them.

## Model

For each remaining session, each driver's result is drawn from their own
results this season. A result counts half as much after 8 rounds, and sprint
results count half as much as races. A non-classification in the pool means a
retirement, so each driver's reliability carries forward. Team-mates' results
are mixed in with one race-equivalent of weight, so a replacement driver starts
from the car's form.

Each team's and each driver's form then follows a random walk through the rest
of the season. Form does not add places to a result. It shifts which of the
driver's own results is drawn: a driver whose form drifts up draws more of
their best results (and fewer retirements), and one whose form drifts down
draws more of their worst. The step per round is 0.3 for teams and 0.45 for
drivers, on a logistic scale of the result's quantile. A tiebreak of 0.5
places separates drivers who drew the same result, and the draws are ranked.

20,000 seasons are simulated with a fixed seed. Final positions break points
ties on wins, then at random. The settings are in `OddsSettings` in
`src/championship_odds.py`.

The table marks a driver **eliminated** when even winning every remaining
session cannot reach the leader's current total, and **clinched** when nobody
else can reach the leader. Otherwise a simulated 0% or 100% is shown as
`<0.1%` or `>99.9%`, because the title is still mathematically open.

## Why the model changed

The first version added noise in finishing places to each draw: a per-session
driver noise (2 places), a team shock (1 place) and a team drift of 1 place a
round. Nobody can finish above P1, so this noise could only move a front-runner
backwards. Backtested, it underestimated the remaining points of the driver
leading on points per race by 28 points on average, and any driver who was
scoring like a champion, including one mounting a late charge, was held back
with them. Recent form was checked as a fix and does not help: shorter form
half-lives were worse, and over 2021–2026 the last four races barely predict
the rest of a season beyond the season average (and not at all in 2021 and
2022). The original model is kept as `pace_mode='places'` for comparison.

## Backtest

`python -m scripts.benchmark_championship_odds --root <app data root>` cuts
every season in the historical library after each round from round 6 and
simulates the races and sprints that were actually run afterwards. A season in
progress is scored against its latest archived round. The promotion score is
the title Brier score plus the top-3 Brier score, summed over drivers and
averaged over cuts (lower is better).

Settings were tuned on 2021–2023. 2024–2026 were reported during the same
sweep, so they are a check, not untouched holdout evidence. 96 cuts, 20,000
simulations, mean of three seeds (seed-to-seed spread under 0.002):

| Seasons | Score | Original | Current | Change |
| --- | --- | ---: | ---: | ---: |
| 2021–2023 | Title + top-3 Brier | 0.598 | 0.547 | −8.6% |
| 2024–2026 | Title + top-3 Brier | 0.685 | 0.627 | −8.5% |
| 2021–2023 | Title Brier | 0.169 | 0.146 | −13.6% |
| 2024–2026 | Title Brier | 0.380 | 0.315 | −17.1% |
| 2024–2026 | Top-3 Brier | 0.305 | 0.312 | +2.2% |
| 2021–2023 | Champion log loss | 0.287 | 0.257 | −10.4% |
| 2024–2026 | Champion log loss | 0.627 | 0.486 | −22.5% |
| 2021–2023 | Remaining points MAE | 17.04 | 15.22 | −10.7% |
| 2024–2026 | Remaining points MAE | 17.60 | 17.56 | −0.2% |
| 2021–2023 | P10–P90 coverage | 85.7% | 86.4% | |
| 2024–2026 | P10–P90 coverage | 83.0% | 80.7% | |

For reference, extrapolating points per race scores a remaining-points MAE of
14.3 (2021–2023) and 17.7 (2024–2026) and gives no probabilities.

In the 18 cuts where the eventual champion was not leading (Verstappen in
2021, Norris in 2025), the champion's average title chance rose from 25% to
33%. Verstappen's 2025 charge is still not anticipated: after round 18 he
stays at 2% (Piastri 74%, Norris 24%, previously 81% and 16%). His surge
came from a mid-season car step that his earlier results did not show, and
widening the drift enough to cover it made every other season worse.

An earlier Plackett–Luce strength fit was rejected: one incident-affected
finish (for example P15 for a race winner) pulled strengths down sharply, and it
was worse than the baseline in both seasons.

## Limitations

- Form only: no circuit traits, grid penalties, weather or the race
  simulator's pace model. A later version could use a saved forecast for the
  next race.
- Driver changes after the latest race are not known until they race.
- Penalties applied to the standings outside the classifications are not
  represented.
