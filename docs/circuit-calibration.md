# Circuit evidence and inactive estimates

Run from `C:\code_project\f1-sim` using the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m scripts.calibrate_circuits `
  --workspace C:\Users\kyle_\AppData\Local\RaceWorkbench `
  --years 2021 2022 2023 2024 2025 2026 `
  --output-dir outputs\circuit_calibration\<new-run-name>
```

This reads completed detailed race partitions, verifies consumed CSV hashes,
and writes a new report folder. It does not fetch data, train/activate a model,
change track profiles, post to Discord, or rewrite forecasts. Existing report
directories cannot be overwritten. No executable rebuild is needed to run this
separate analysis command; the desktop profile preview still shows active values.

`report.html` is a readable evidence table; `candidate_profiles.csv` is a flattened
export. `report.json` includes observations, exclusions, sample counts, method
assumptions, input hashes, benchmark predictions and scores. `provenance.json`
records analysis-source and generated-artifact hashes.

## What is estimated

Full safety-car and red-flag occurrence are binary per-race observations from the
raw track-status feed, codes 4 and 5 respectively. VSC codes 6/7 are recorded
separately. The window spans the first recorded lap start through the first
finish on the maximum completed lap. The feed's state at window start counts;
ended pre-start and post-finish events do not. Missing initial status or timing
is unknown, not an event-free race. Most older downloads lack session-status
tables, so this lap-derived window and the feed's completeness remain explicit
limitations. Aborted classifications such as Belgium 2021 are excluded.

Estimates use a Beta-binomial shrinkage model. The pooled rate has four
default-centred pseudo-races; each layout shrinks toward that pooled rate with
four pseudo-races. Displayed intervals are 90% marginal Bayesian credible
intervals conditional on that model, not guarantees or validation certificates.
Chronological benchmark predictions compute both priors from earlier races only.
The historical pool includes earlier observations of the target circuit.

Circuit/layout identity comes from each saved manifest. The analysis explicitly
recognises the saved Yas Island location as Yas Marina for an Abu Dhabi event,
without modifying those manifests. Conflicts remain excluded. Melbourne is split
at 2022, alongside the registry's Barcelona and Singapore layout splits. The
registry does not encode every resurfacing, DRS change or corner modification.
Unobserved layouts have missing candidate values rather than inherited local
counts. Pooled shrinkage remains an assumption across regulations and conditions.

## Overtaking evidence is a separate measurement

Archived lap exports have timing but no race Position field. The analysis counts
adjacent-driver order reversals at the timing line across the same numbered
laps, using lap start plus duration. Both drivers must have accurate, undeleted,
non-pit, completely green laps on both sides of the comparison. The opening lap
is excluded and both crossing gaps must be within 15 seconds. Exposure is the
number of eligible nearby pair-lap comparisons.

This is a **clean order-change proxy**, not official overtakes: passes reversed
within a lap disappear, same-numbered lap comparisons do not reconstruct the
whole real-time field, and lapping/retirements remain limitations. Gamma-Poisson
shrinkage uses 500 pooled pseudo-pair-laps; intervals condition on independent
counts and a fixed pooled prior. Serial dependence and race-to-race variation
can make those intervals too narrow. No arbitrary mapping to simulation
`OvertakingDifficulty` is written: that parameter scales grid loss and requires
a separate simulation parameter fit and finishing-order comparison.

Similarly, observed red-flag occurrence is not automatically the simulation's
`RedFlagBaseChance`, which is subsequently adjusted for weather and race-control
information. This report does not silently substitute these two quantities.

## Diagnostic result, 23 October 2026

The downloaded 2021–2026 archive supplied 125 included races across 26 circuits.
Six were excluded: five unresolved physical venues and the aborted Belgian race.
There are 108 scored race predictions from 2022 onward. The 2026 section is a
rolling earlier-races comparison, not an untouched holdout. These races have
already been inspected and provide no fresh promotion evidence.

| Metric, Brier score (lower is better) | Generic | Active profiles | Earlier pooled | Earlier layout shrinkage |
| --- | ---: | ---: | ---: | ---: |
| Full safety-car occurrence | 0.26926 | 0.25625 | 0.25356 | 0.26326 |
| Red-flag occurrence | 0.11317 | 0.11084 | 0.11037 | 0.11706 |

Circuit shrinkage does not consistently beat the active profiles or pooled
baseline. Its red-flag log loss improves over the active profiles, while Brier
worsens; that mixed result does not establish a robust uplift. The 2026 sample
is small and cannot rescue a failed full-period comparison by itself.

**Decision: retain these estimates as inactive evidence.** Active CSV values and
their `generic_uncalibrated`/heuristic labels remain accurate. The next model
experiment should fit and benchmark the grid-loss coefficient independently,
then collect prospective evidence; event-rate scoring alone cannot justify a
change to finishing predictions.

## Calibrated track factors candidate (`calibrated_v1`)

`data/track_calibration/track_calibration_v1.csv` holds one row per current
layout with a calibrated safety-car chance and overtaking difficulty. Set
`model.track_profile_model` to `calibrated_v1` to use them; the default
`active` leaves `track_profiles.csv` values and every forecast unchanged.
It is a local-only candidate like the others in
[simulation-candidates.md](simulation-candidates.md). Red-flag base chances are
not changed, for the reason given above.

Rebuild it from a report and the archive (writes a new file only):

```powershell
.\.venv\Scripts\python.exe -m scripts.build_track_calibration `
  --report outputs\circuit_calibration\20261023-reviewed\report.json `
  --save-grid-stats data\track_calibration\race_grid_order_<run>.csv `
  --output data\track_calibration\track_calibration_<new>.csv
```

**Safety car.** Re-scoring the same 108 chronological predictions with
stronger layout shrinkage shows that circuit history adds almost nothing over
the pooled rate (about 56% of races):

| Layout prior strength (pseudo-races) | Brier, all | Brier, 2026 |
| --- | ---: | ---: |
| 4 (report default) | 0.2633 | 0.2611 |
| 12 | 0.2551 | 0.2545 |
| 20 (used) | 0.2540 | 0.2533 |
| Pooled only | 0.2536 | 0.2525 |
| Active profiles | 0.2563 | 0.2897 |

So each layout is shrunk with 20 pseudo-races toward the pooled rate. The
result is mostly a level correction: the active profiles average 42% against
a 56% observed rate, and 2026 races punish that gap most.

**Overtaking difficulty.** Two measures from the same 125 races are averaged as
weighted z-scores: grid-to-finish rank correlation of classified finishers
(higher means grid order holds) and the clean order-change proxy (fewer
reversals means harder). The index is shrunk by race count (three
pseudo-races) and mapped to the existing scale by a linear fit to the 14
heuristic layouts (correlation 0.58), clipped to 0.35–0.90. Only the 13
generic placeholder circuits receive a fitted value; heuristic rows keep
theirs. The weak anchor correlation pulls fitted values toward 0.61, which is
the honest amount of signal. Notable results: Suzuka and Madring 0.70, Red Bull
Ring 0.67, Miami 0.65, Las Vegas 0.44, Austin 0.53. Madring and Sepang have
one race each. The per-race grid statistics are saved in
`data/track_calibration/race_grid_order_2021_2026.csv`.

**Benchmark (diagnostic only).** `python -m scripts.benchmark_safety_car --arms
established track_sc_v1 calibrated_sc calibrated_overtaking calibrated_v1`,
2026 rounds 4–16, 5,000 sims, seeds 42/123/777:

| Arm | Finish MAE | Win Brier | Podium Brier | Top-10 Brier |
| --- | ---: | ---: | ---: | ---: |
| Established engine | 3.664 | 0.0307 | 0.0730 | 0.1846 |
| `track_sc_v1`, active SC chances | 3.671 | 0.0303 | 0.0722 | 0.1791 |
| `track_sc_v1`, calibrated SC chances | 3.676 | 0.0300 | 0.0722 | 0.1776 |
| Calibrated overtaking only | 3.649 | 0.0303 | 0.0729 | 0.1839 |
| Calibrated SC and overtaking | 3.662 | 0.0296 | 0.0720 | 0.1769 |

Calibrated SC chances beat the active ones on top-10 Brier in 11 of 13 races.
Overtaking changes only touch five of these races (Miami, Austria, Belgium,
Madring, Baku) and most of the finish-MAE gain is Madring. These races are
inside the calibration data and already inspected, and the combined top-10
gain (4.2%) is below the 5% gate, so the candidate stays off by default.
