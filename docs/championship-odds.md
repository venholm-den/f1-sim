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

Draws are re-ranked with three noise terms, in finishing places:

| Term | Standard deviation | Purpose |
| --- | ---: | --- |
| Driver noise per session | 2.0 | Separates drivers who drew similar results |
| Team shock per session | 1.0 | Team-mates move together on a given weekend |
| Team drift per round (random walk) | 1.0 | Car development; keeps long horizons from becoming overconfident |

20,000 seasons are simulated with a fixed seed. Final positions break points
ties on wins, then at random. The settings are in `OddsSettings` in
`src/championship_odds.py`.

The table marks a driver **eliminated** when even winning every remaining
session cannot reach the leader's current total, and **clinched** when nobody
else can reach the leader. Otherwise a simulated 0% or 100% is shown as
`<0.1%` or `>99.9%`, because the title is still mathematically open.

## Backtest

The settings were chosen on the 2025 and 2026 archives by cutting each season
after a round and simulating the rest. Mean absolute error compares each
driver's expected remaining points with what they actually scored. The
baseline extrapolates points per race so far and gives no probabilities.

| Season | Cut after rounds | Model MAE | Points-per-race MAE |
| --- | --- | ---: | ---: |
| 2025 | 8, 12, 16, 18, 20 | 17.6 | 17.8 |
| 2026 | 6, 8, 11, 14 | 13.5 | 13.2 |

Expected points are about as accurate as the simple extrapolation. The model
adds full distributions, team correlation and title probabilities. In 2025,
after round 18 it gave Piastri 81%, Norris 17% and Verstappen 2%; Norris won
by two points from Verstappen. That is one season, so treat late surges such
as Verstappen's as under-weighted.

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
