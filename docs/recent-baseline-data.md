# Recent race baseline data

Build a versioned same-season dataset for the upcoming race:

```powershell
cd C:\code_project\f1-sim
.\.venv\Scripts\python.exe -m scripts.build_recent_baselines
```

The default requests up to 16 prior races from the target season. Select an
explicit target with `--year 2026 --target-round 17`; use `--races 8` for a narrower
recent sample. An optional `--cutoff-utc` must include a timezone and cannot be in
the future. For historical targets the cutoff is capped at the target race start.

Each run creates a new directory under `data/recent_baselines/<timestamp>/`.
Supplying an existing output directory fails instead of replacing it. Existing
`data/historical_model` files, trained artifacts, frozen forecasts and Discord
receipts are preserved. FastF1's normal source cache is populated/reused.

## Contents

- Normalized laps, classification, inferred actual tyre strategy, observed race
  weather and race-control context, compatible with the historical dataset column
  conventions. Telemetry downloads and OpenF1 enrichment are not required.
- Legacy driver-race pace features with source year, round, event and UTC start.
- Per-race classification/lap/feature coverage, plus drivers lacking usable pace
  and samples below five clean laps. Missing pace is retained as unknown in the
  coverage table; it is not silently made neutral or treated as a mechanical failure.
- 2-, 5- and 8-race weighted baseline summaries using the existing recency formula,
  with per-driver sample counts. Wider windows use only the available same-season
  races and report shortfall explicitly.
- Race manifests, a readable report and SHA-256 fingerprints of CSV outputs and
  the feature/aggregation source. Failed acquisitions are listed in the manifest;
  rate limiting stops acquisition rather than repeatedly hammering the provider.

Each candidate must precede the target round and leave at least eight hours
between its scheduled start and the cutoff. The session must also have a terminal
`Finished`/`Finalised`/`Ends` state, complete unique classification positions and
driver identifiers, and usable lap data. A cached directory or scheduled race
date alone is insufficient evidence of completion. The live recent-race loader
now uses the same completion/classification gate before accepting a baseline.

## Interpretation

The latest completed classification supplies an **assumed** next-race roster for
window summaries; target-session classifications still control live forecast
rosters when available. Historic substitutes remain in the full dataset but do
not automatically join the assumed current roster.

The builder does not retrain models, increase the automated two-race setting,
change recency weights, enable experimental candidates or post to Discord. Newly
available completed races can be used by the existing loader when the next
forecast is generated. The existing Singapore PRE snapshot remains as originally
frozen; it is not rewritten with later Bahrain data.

Observed past-race weather belongs to that race's baseline context, not the target
race's forecast. Historical feeds can contain later corrections; these local
capture timestamps do not prove original publication times. Legacy pace, inferred
degradation and DNF features remain heuristic. Wider coverage is useful input and
supports future testing; it does not establish improved prediction accuracy.

Any change from two to five or eight live baseline races should be evaluated
chronologically against the current configuration under the promotion gates in
`docs/accuracy-improvements.md`. Do not count races whose results have already been
inspected as untouched validation data.
