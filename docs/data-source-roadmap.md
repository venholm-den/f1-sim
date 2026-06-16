# Data Source Roadmap

## Current Source

FastF1 remains the core modelling source for:

- sessions
- laps
- qualifying results
- race results
- weather
- timing-derived features

## OpenF1 Roadmap

OpenF1 support is scaffolded in:

```text
src/data_sources/openf1.py
```

Planned uses:

- `/position` for live or near-live running order.
- `/intervals` for gap context in reports.
- `/pit` for pit stop timing.
- `/stints` for compound and tyre-age context.
- `/race_control` for yellow flag, safety car, red flag, and incident context.

The next useful integration point is report context rather than core prediction.
Live data should explain what is happening without replacing the current FastF1-based model pipeline.

## FIA Document Roadmap

FIA document support is scaffolded in:

```text
src/data_sources/fia_documents.py
data/fia_documents/fia_document_index.csv
```

Highest-value uses:

- Official starting grid and penalties into `src/grid.py`.
- Classification cross-checks for `src/backtest.py`.
- Summons and steward notes surfaced in report commentary.

## Generated Roadmap CSV

Create or refresh the machine-readable roadmap with:

```powershell
python scripts/build_data_source_roadmap.py
```
