# Data Sources

## FastF1

FastF1 is the primary motorsport data source.

Used for:

- Event schedule.
- Session laps.
- Session weather.
- Session results/classification.
- Race-control messages when available.
- Track/lap telemetry for circuit layout rendering.

Notes:

- First loads can be slow.
- FastF1 can hit API rate limits during large historical extraction.
- Cache data is local and ignored by Git.

## Open-Meteo

Open-Meteo is used as a forecast fallback when FastF1 session weather is unavailable and track coordinates are available.

Inputs:

- `Latitude` and `Longitude` from `data\track_profiles.csv`.
- Event/session timing context where available.

Config:

- `model.use_weather_forecast`

## OpenF1

OpenF1 support exists under `src\data_sources\openf1.py` and in the historical extraction path.

Current use:

- Optional supplemental historical data extraction.
- Placeholder/empty output files are tolerated when OpenF1 data is unavailable.

Disable for historical extraction with:

```powershell
python scripts/build_historical_dataset.py --no-openf1
```

## FIA Document Index

The project does not scrape FIA documents automatically. Instead, it reads a local index:

```text
data\fia_documents\fia_document_index.csv
```

Used for:

- Official grid context.
- Penalty notes.
- Classification/context records.

## Local CSV Data

| File | Purpose |
| --- | --- |
| `data\fantasy_prices.csv` | Fantasy value and xPPM metrics. |
| `data\track_profiles.csv` | Track assumptions and forecast coordinates. |
| `data\team_power_units.csv` | Reliability inference by team and power-unit supplier. |
| `data\fia_documents\fia_document_index.csv` | FIA official context. |

## Historical Training Data

The historical model builder combines FastF1 race results, qualifying laps, weather summaries, race-control summaries, and actual strategy/stint summaries into local CSVs under:

```text
data\historical_model\
```

The model trainer writes sklearn/joblib artifacts under:

```text
data\models\
```

Both directories are ignored by Git because they are generated and can be large.

## Reliability Data

There is no official engine/car reliability feed in the repo.

Reliability is inferred from:

- Recent race result statuses.
- Mechanical/non-mechanical status keyword classification.
- Team and power-unit mapping in `data\team_power_units.csv`.
- Trained historical DNF model probability when available.

## Track Visual Data

Track layout rendering uses FastF1 lap telemetry when available. If telemetry is missing, the app falls back to empty/placeholder map data rather than using static diagram images.
