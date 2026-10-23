# Expanded reference datasets

Updated from public source snapshots on 5 October 2026. The source CSVs and the
portable app's starter datasets use the same schemas. Existing original files
were retained under `outputs/reference_data_update/20261005/before`.

| Dataset | Previous rows | Updated rows | Coverage |
| --- | ---: | ---: | --- |
| `data/track_profiles.csv` | 13 | 79 | 78 physical circuits, with existing event aliases retained |
| `data/team_power_units.csv` | 29 | 1,368 | Engine/supplier lookup rows across 1950–2026, including aliases |
| `data/fia_documents/fia_document_index.csv` | 814 | 9,252 | 172 event-season combinations across 2019–2026 |

## Track profiles

The [Jolpica circuit catalogue](https://api.jolpi.ca/ergast/f1/circuits.json?limit=100)
supplies circuit IDs, names, coordinates, countries and localities. Its race
calendar supplies observed first/last seasons and commercial event-name aliases.
`FirstSeason` and `LastSeason` describe the downloaded calendar, including
scheduled events; they are not guarantees of a completed race. Historical
circuits and reused Grand Prix names remain separate through `CircuitId`.

Official Formula 1 race pages add published circuit length, race laps, race
distance and first Grand Prix for 26 circuits. `GeometrySeason` and
`GeometrySourceURL` identify the applicable published edition. Those geometry
values must not be applied to every historical layout. For example, the
[2026 Bahrain page](https://www.formula1.com/en/racing/2026/bahrain) describes
Sepang; Sakhir's geometry comes from the 2025 Bahrain page.

The original 13 overtaking/safety-car/red-flag values are preserved as
`existing_circuit_heuristic`. Added circuits use the existing generic defaults,
explicitly marked `generic_uncalibrated`. The added reference data does not
pretend to measure circuit-specific overtaking or incident probabilities.

The CSV is a wider reference catalogue than the forecasting venue resolver.
Forecasts still require a supported, unambiguous physical venue and layout;
adding an archive circuit does not silently resolve ambiguous historical race
names or qualify that circuit for a calibrated forecast.

## Engine and power-unit mappings

Sources are the official Formula 1 [historical team standings](https://www.formula1.com/en/results/1958/team)
and, before the constructors' championship, published driver standings. These
sources are not a census of every non-scoring/non-qualifying entrant. Before
2014, the field describes an engine rather than a hybrid power unit.

`EngineBadge` retains the published brand; `OfficialTeamLabel`, `SourceURL` and
`VerifiedAtUTC` preserve attribution. Where the standings label includes an
engine suffix, a short team-name alias is added only when it identifies one
supplier for that season. Ambiguous multi-engine aliases, such as 1963 Lotus,
are omitted; engine-qualified names remain available.

TAG Heuer-badged 2016–2018 Renault units are grouped under Renault, with the
[official naming partnership](https://www.formula1.com/en/latest/article/red-bull-and-tag-heuer-extend-engine-naming-partnership.37dnjbA2VWSMgUlN7E1bYL)
recorded separately. Other historical badge names are preserved rather than
assuming manufacturer relationships. This is a supplier/brand reference, not an
engine specification, power output or reliability measurement.

The retained current-year mappings are checked against the
[2025 FIA entry list](https://www.fia.com/sites/default/files/media_kit_-_2025_singapore_grand_prix_0.pdf)
and the [2026 F1 supplier explanation](https://www.formula1.com/en/latest/article/all-you-need-to-know-about-f1s-new-power-units.14jfv7a36905uDJDdNyfQd).
Lookup aliases do not assert separate entrants. Bare customer-team labels in
2025/2026 standings are not interpreted as works engines. A missing requested
season now returns `Unknown`, rather than borrowing a past or future supplier.

Four historical labels remain unresolved from the collected source pages:
1975 Frank Williams Racing Cars/Williams, 1993 Sauber, and 1998/1999 Arrows.

## FIA documents

The [FIA decision-documents archive](https://www.fia.com/documents/championships/fia-formula-one-world-championship-14/season/season-2026-2072)
was traversed through every event page offered for 2019–2026. Titles, available
document numbers, publication times, session/type and direct PDF URLs are stored.
Older listings without document numbers now import correctly. Sprint session
labels follow their season: the 2021 sprint qualifying race is `S`, while the
2023 shootout and later sprint qualifying sessions are `SQ`.

These 9,252 rows have `status=metadata`. PDFs have **not** been bulk downloaded
or parsed into driver grids, penalties or classifications. Blank driver/penalty
fields remain blank. Archive pages do not expose complete 2016–2018 coverage;
the 2015 filter returned a misfiled 2024 document, which was quarantined in the
update report. The 2026 archive includes documents published so far, not a
complete future season. No document or competitor outcome was invented.

## Reproduce and verify

The refresh script uses the existing Python environment and three concurrent
public requests at most. All acquired pages are cached with source URLs and
retrieval hashes in the selected output directory. Use a **new** output folder
to obtain a fresh snapshot; reuse one to resume/reparse existing snapshots.

```powershell
.\.venv\Scripts\python.exe -m scripts.refresh_reference_data --output outputs/reference_data_update/new-snapshot --collect --build --apply
```

Without `--apply`, files are staged for inspection. Applying validates all three
files first, retains originals and atomically replaces each CSV. Existing source
provenance and unrelated datasets are preserved. Network/coverage failures,
ambiguous aliases and quarantined listings are reported in JSON beside the
snapshots. The FIA single-season CLI also supports configured season IDs from
2019 through 2026.

The update does not train a model or establish a prediction-accuracy gain.
Frozen forecasts and Discord delivery receipts remain unchanged.
