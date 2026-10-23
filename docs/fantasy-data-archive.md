# Weekly Fantasy prices and actual scores

The Fantasy page now has a source-labelled archive, season/Grand Prix/asset/source filters, current official market prices, and **Refresh selected season**, **Download all seasons**, and **Open CSV archive** controls. Existing simulation projections retain the project's scoring assumptions and remain separate from collected actual scores. Chips, personal team multipliers and transfer penalties are not included in the collected asset scores.

Public data sources:

- Official [F1 Fantasy statistics](https://fantasy.formula1.com/en/statistics): the public schedule and `feeds/drivers/{gameweek}_en.json` feeds used by its web app, containing drivers, constructors, quotes and gameweek/session/season points. Current and latest completed gameweeks are collected.
- [F1 Fantasy Tools statistics](https://f1fantasytools.com/statistics): its public `/api/statistics/{year}` endpoint used by the season selector. It exposes 2023 onward. 2021 and 2022 are unavailable through this source. No login, private export API or credentials are used.

The existing hourly `scripts.auto_forecast` command checks collection independently of forecast eligibility and post-race-only mode. Successful current-season collection is throttled to six hours; failed sources retry after one hour and do not prevent forecasts or replace their last successful data. Older completed seasons download once unless explicitly refreshed. `--check-only` performs no Fantasy collection. Discord delivery and existing frozen forecasts are unchanged.

Run a backfill:

```powershell
.\.venv\Scripts\python.exe -m scripts.refresh_fantasy_data --years 2023 2024 2025 2026
```

Add `--force` to recheck already downloaded seasons. The default workspace is the main project. `--workspace` allows an explicit archive workspace. The desktop reads the configured PC automation workspace when available, falling back to its local workspace, and polls the archive while Fantasy is open.

## Files and provenance

`data/fantasy_market/weekly_history.csv` is a convenient export of the latest source records. Each immutable `captures/<capture>/` directory contains `raw.json`, normalized `rows.csv`, and a manifest with UTC capture time, source URL and SHA-256 checksums. `index.json` atomically selects the latest successful captures. Source corrections create new captures; previous captures remain available. Corrupt normalized captures are rejected by readers. The local archive is ignored by Git.

Rows are identified by source, season, source round, asset type and source asset ID. Both sources remain visible independently, including disagreements and historical substitute drivers. Source Grand Prix names/countries/race dates are retained; a simulator venue override does not silently remap the Fantasy source calendar. A historical capture made today is not evidence that a price or result was known before that race.

Official incomplete gameweeks are marked **provisional**. Missing scores stay blank; genuine zero and negative scores are preserved. Empty future rounds do not generate zero-point actual results. Historical `price` and `priceChange` retain the source-reported meaning; no unsupported pre-race/post-race transformation is made.

## New forecast value calculations

New PC forecasts may use a captured official driver quote only when its season and event match, it was captured before simulation time, the race is still in the future and the capture is less than seven days old. The run writes `fantasy_market_prices.csv` with per-driver source URL and capture time, and automated forecasts freeze that file alongside their summary. The manual price template remains the fallback. Historical round prices and actual scores do not enter race probabilities, model training or retrospective value estimates. Existing frozen values remain unchanged.

## Initial verified coverage

11 October 2026: 86 completed weekends across 2023–2026, 2,831 source records including the latest completed and current provisional official feeds, with driver and constructor coverage. This count can increase as the season progresses. The review evidence is under `outputs/fantasy_data/20261011/`.

The setup session controls also follow the schedule's session slots: standard weekends `PRE → FP1 → FP2 → FP3 → Q → R`, modern sprint weekends `PRE → FP1 → SQ → S → Q → R`, and historical sprint weekends in their original order.
