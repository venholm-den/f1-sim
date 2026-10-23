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
