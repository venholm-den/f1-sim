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

The project reads a local index of FIA documents:

```text
data\fia_documents\fia_document_index.csv
```

Populate or refresh it from the official FIA Formula 1 decision-documents page:

```powershell
python scripts/update_fia_document_index.py --year 2026
```

To refresh one event only:

```powershell
python scripts/update_fia_document_index.py --year 2026 --event "Hungarian Grand Prix"
```

The default updater fetches document metadata such as event, FIA document number,
title, published time, URL, and coarse document type. Add `--enrich-pdfs` to
download selected PDFs and parse grid, classification, summons, and steward rows
where the PDF text is structured enough:

```powershell
python scripts/update_fia_document_index.py --year 2026 --event "Hungarian Grand Prix" --enrich-pdfs
```

PDF enrichment can use an optional driver map CSV with `car_number`, `driver`,
and `team` columns when FIA PDFs contain car numbers/full names instead of the
three-letter driver codes used by the simulator:

```powershell
python scripts/update_fia_document_index.py --year 2026 --enrich-pdfs --driver-map data\fia_documents\driver_map.csv
```

Downloaded PDFs are cached under `data\fia_documents\cache\`, which is ignored by
Git. Commit the CSV facts and source URLs, not the cached FIA PDFs.

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
