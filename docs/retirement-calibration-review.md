# Retirement labels and matched model review, 26 October 2026

This is offline research. The protected scheduled runtime, its four-arm suite,
live defaults, old forecasts and old score files are preserved. Source fixes
apply to newly computed development scores and inactive model candidates; they
do not revise previously published performance records.

## Label audit

The audit reads checksum-verified saved race classifications. `Status` alone
missed 15 retirements marked `R`: two in 2021, ten in 2022, one in 2023 and two
in 2026. These include status text such as `Turbo`, `Wheel nut`, `Undertray`
and `Lapped`. Two 2021 withdrawn entries had mechanical/illness status text and
were counted as retirements by the season model. They are excluded from this
target. The earlier archive-replay rule also treated 37 unknown/non-starting/DQ
entries as retirements and inferred retirement from a deficit of four laps.

Four numeric-classification/lap-deficit cases were checked against primary
reports. Two were genuine late retirements: [Zhou, France 2022](https://www.formula1.com/en/latest/article/zhou-says-he-was-struggling-all-that-way-through-french-grand-prix-before.5vUweAZtjDua4x9mFuT8G7)
and [Norris, Austria 2024](https://api.fia.com/news/f1-george-russell-takes-surprise-austria-win-verstappen-and-norris-collide).
Two were finishers: [Stroll and Bottas, Canada 2026](https://www.fia.com/news/f1-antonelli-wins-thrilling-canadian-grand-prix-ahead-hamilton-and-verstappen-russell-retires).
Thus status-only labels missed **17** verified retirements in total (15 marked
R plus two late retirements), while the old archive rule falsely counted two
confirmed finishers and 37 unknown/excluded entries as retirements.

`data/retirement_labels/verified_outcomes_v1.csv` preserves these four reviewed
annotations, primary URLs and expected original provider values. Normalisation
adds `VerifiedRetirement` in memory without changing raw files, status, cause
or finishing positions. A changed provider row fails the annotation check and
requires review. Both final benchmarks include this evidence file in their
fingerprints. The earlier status/classification-only benchmark and its exact
source are retained as a first-pass sensitivity check.

`src.result_status.retirement_outcome` is the shared row-level policy:

- Non-starting/withdrawn, disqualified, excluded and failed-to-qualify entries
  have an unknown retirement label for this model and are excluded from Brier
  and calibration denominators. They are not healthy mechanical observations.
- Classification `R` establishes a retirement even when status says `Lapped`
  or the cause is unrecognised. An unrecognised cause stays unspecified.
- Verified primary-source annotations resolve the reviewed late-retirement
  cases and negative controls before falling back to status/classification.
- Recognised retirement status counts even with a numeric classification.
- A recognised finisher/lapped status counts as finished; a lap deficit alone
  cannot establish whether a car stopped before the finish.
- A numeric classification without a known status is not silently turned into
  a finisher. Other unknowns remain unknown and are counted explicitly.

The installed FastF1 `SessionResults` documentation defines `R` as retired,
`D` as disqualified, `E` as excluded, `W` as withdrawn, `F` as failed to qualify
and `N` as not classified. Classification and physical retirement are separate
concepts. See [FastF1 SessionResults](https://docs.fastf1.dev/core.html#fastf1.core.SessionResults).

The row policy now feeds retrospective replay, new source backtests, feature
ablation scoring and inactive all-cause/season retirement training. New form
history packets retain `ClassifiedPosition` and `VerifiedRetirement`, so their
separate retirement prior can use the same labels. Older packets without those columns retain status-only
fallback; their frozen bytes are never changed. The season and all-cause
candidate metadata identifies a new experimental label version.

This is a bounded repair of detected conflicts, not proof that every numeric
classification identifies physical retirement correctly. Other late retirements
can still need terminal timing or published report evidence. A numeric result
and a lap deficit do not, by themselves, establish whether a driver finished.

## Declared retirement comparison

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_retirement_models `
  --workspace "$env:LOCALAPPDATA\RaceWorkbench" `
  --output-dir outputs/retirement_review/NEW_RUN/retirement
```

Three independent arms: established, `all_cause_dnf_v2`, `season_dnf_v1`.
Each uses 5,000 simulations for seeds 42/123/777, five earlier races for pace,
and the same 30 earlier races for candidate retirement history. The season
model then applies its existing current/two-prior-season filter. No settings
are searched. This matches the application's five-race pace default and
30-race retirement-history setting. The first five archived races supply
warm-up history rather than scored episodes.

PRE, FP2 and Q remain separate, on identical complete-driver episodes across
arms. Missing/incomplete qualifying classifications remain excluded; Q order
is never imputed from lap times or a later Sunday grid. Malformed target race
classifications are excluded by the full-distribution scoring contract.
Development is 2021–2024. All 2025–2026 results are previously inspected
diagnostics, with zero fresh promotion races.

The report retains full RPS, threshold RPS, win/podium/top-10/DNF Brier,
finishing error for all drivers and finishers, log/head-to-head scores and
expected/actual retirements. Expected retirement counts paired with actuals
use known-label drivers only; a separate column retains whole-field expected
retirements. Calibration bins average seed predictions before counting unique
driver/races. Scores average seeds within each race and then weight races
equally. Paired 95% intervals resample whole races.

The historical screen requires development selection, at least six matched
later races per stage, at least 5% lower paired RPS, no outcome-Brier regression,
no clearly worse finish MAE and Q beating qualifying order. A pass means
collect fresh evidence separately; it never activates a live model or adds an
arm to the existing four-model suite.

## Independent form/risk rebenchmark

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_form_adjustment `
  --workspace "$env:LOCALAPPDATA\RaceWorkbench" `
  --output-dir outputs/retirement_review/NEW_RUN/form
```

This repeats the original fixed five-arm experiment at 2,000 simulations per
seed, retaining its original two-race pace-history protocol. Its results must
be compared within this experiment, not numerically pooled with the five-race
retirement comparison. It refits only on strictly earlier outcomes and retains
the degradation-only control to isolate the additional contribution of form.
Its original diagnostic screen is retained for reproducibility; current live
promotion still requires the separate RPS/fresh-race review.

An additional fixed `--history 5` run checks transfer to the application's
current five-race pace baseline. The same arms, 2,000 simulations and three
seeds are retained, with no parameter search. Decisions about resuming research
on current application inputs use this run; a pass on the old two-race
protocol alone is insufficient. Controls remain matched within each run.

Registration or deployment of a new independent cohort is a separate decision
after reviewing its stage-specific results. The protected runtime's existing
form/risk hook remains blocked; this work does not bypass its source/benchmark
gate or change its sealed configuration.

## Evidence

Local outputs are append-only under
`outputs/retirement_review/20261026T231423`: original-policy row audit, corrected
label audit, protocols, per-seed and per-race scores, predictions, calibration,
coverage exclusions, source/input hashes and independent form results.
Final runs are `retirement-verified`, `form-verified` (two-race reproduction)
and `form-live-history` (five-race sensitivity); `retirement`, `form`
and `first-pass-source` preserve the initial sensitivity run.
Old artifacts remain available alongside these new outputs.
