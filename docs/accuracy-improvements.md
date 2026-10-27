# Accuracy improvements and validation

[Grid-slot retirements, Driver of the Day and the Rhter Mexico comparison, 27 October](season-grid-retirements.md)
adds an experimental retirement model that accounts for where each car
starts, tests a ten-race pace history, and refits Driver of the Day on real
fan votes. With ten races of history the retirement model clears the 5%
paired-RPS bar at every stage on replay, and both are now the defaults.

[Retirement calibration review, 26 October](retirement-calibration-review.md)
audits status/classification disagreements and compares established, all-cause
and season-based retirement models separately for PRE/FP2/Q. It also repeats
the independent form/risk benchmark. Source label fixes do not rewrite old
scores, deploy a model or change the protected scheduled cohort.

[Stage-specific form and retirement shadows](form-and-retirement-shadows.md)
implement the historical-factor follow-up in the simulator. PRE/FP2 form plus
degradation and a separate PRE retirement prior now collect independent shadow
evidence. Q candidates remain parked; live settings and the existing trial
cohort are unchanged.

[Historical predictive-factor analysis, 24 October](historical-predictive-factors.md)
audits the complete detailed archive and tests recent form, pace, practice,
reliability, weather and telemetry. Team/driver form is the strongest lead;
the apparent gain over qualifying order still needs fresh confirmation.

[24 October validation recovery and degradation comparison](predictor-validation-recovery.md)
repairs the inspection ledger, replaces the invalid source-pinned cohort without
rewriting it, and reports the fixed PRE/FP2/Q degradation replay. Q still loses
to qualifying order, so no candidate is promoted.

[Promotion lanes, fuller race scores and the season challenger](promotion-lanes-and-challenger.md)
separate factual fixes from accuracy changes, add whole-distribution and
head-to-head scores with a power check, and freeze one combined challenger per
season with a sequential test.

[Pace uncertainty and the tuned shadow settings](pace-uncertainty.md) samples
each car's pace per team and per driver in the car-agent engine, adds
heavy-tailed incidents, and registers the tuned pace and grid settings as a
named shadow candidate.

The [single degradation candidate](single-degradation.md) counts tyre wear
once instead of four times and is compared offline against the live engine.

The [23 October cohort and qualifying-pace follow-up](qualifying-pace-followup.md)
preserves the four-arm prospective suite, independently investigates the nine
Q exclusions and defines the next isolated pace comparison.

The [SC/VSC, tyre inventory and classification follow-up](simulation-gap-tests.md)
adds isolated shadow comparisons and timestamped OpenF1 checks without
changing live probabilities.

[Multi-score settings tuning](multi-score-tuning.md) fits five simulation
settings jointly on rank correlation, Brier and calibration error, using
whole earlier seasons for fitting and later seasons for held-out scoring. It
never changes live defaults.

For the latest implementation and experiment settings, see the
[11 October qualifying, pace and retirement revision](model-accuracy-revision.md).

The next [simulation candidates](simulation-candidates.md) add race-window weather,
partial-pooling qualifying pace, explicit pit scenarios and competing-risk survival.
Cached Q classifications can have entirely missing `Position` values: older
`grid_order` diagnostics then use the existing timing-derived fallback, not
official Q order. Archive-backed comparisons must identify their different
classification inputs and cannot be mixed with those older results.

Automatic practice collection and the predeclared three-way prospective comparison are described in [prospective-prediction-trials.md](prospective-prediction-trials.md). They collect fresh evidence without changing live predictions or treating inspected historical races as new validation.

The 11 October follow-up adds an inactive stage-specific learned blend and
prospective shadow collection. See [stage-ensemble.md](stage-ensemble.md) for
inputs, chronological validation, measured diagnostics and source automation.
Live predictions remain on the established formulas pending fresh validation.

## Current decision

### Changes following the 10 October saved-forecast audit

`src/result_status.py` is the shared outcome policy for historical training,
mechanical reliability and benchmark scoring. Lapped finishers are no longer
retirements. Generic retirements retain an unspecified cause; unknown, DNS and
disqualified outcomes no longer count as mechanically healthy observations.
New historical training excludes DNS/disqualified rows, fits retirement targets
on known labels only, and reports unknown-label coverage separately. Existing
artifacts are preserved and candidate output directories cannot be overwritten.

Training now evaluates a regularised change from qualifying order, preserving
that anchor at inference, and exports a coherent score-ranked finishing order.
The absolute-position model remains available through the explicit
`finish_target='absolute'` argument for controlled comparisons. Neither is activated
by training. Default historical calibration is off and the loader rejects inactive
or unreviewed artifacts, including legacy files without promotion metadata.

Three independent experimental candidates are available through
`scripts.benchmark_feature_ablations --variants legacy all_cause_dnf_v2 single_pace_blend_v1 q_grid_3_3_v1`:

- `all_cause_dnf_v2`: time-decayed earlier race outcomes, with team/driver/circuit
  shrinkage toward a population prior. Sparse-data prior is explicitly 10% with
  40 weighted entries; the half-life is eight cached races. Team/driver/circuit
  strengths are 20/12/40; mixture weights are 0.5/0.3/0.2. These are declared test
  assumptions, not estimates fitted to the seven audited races. Cause shares
  retain unspecified outcomes, and lap noise does not affect retirement risk.
- `single_pace_blend_v1`: raw current and historical relative gaps blended once
  using the existing stage race weight times evidence quality. It avoids multiplying
  sequential current/history blends. Missing current/history signals have explicit
  fallback weights; uncertainty, strategy and retirement signals are preserved.
- `q_grid_3_3_v1`: a predeclared Q-only grid multiplier of 3.3, with other stages
  unchanged. It is a modest sensitivity test, not the previously inspected 13.2
  search-boundary result.

These candidates are offline benchmark variants; the normal forecast pipeline
retains its established pace and all-cause risk formulas until the candidates
pass independent promotion review. The mechanical unknown-cause correction is
active in source runs. Do not claim an accuracy uplift from that semantic repair.

Use `scripts.review_audit_models --audit-dir <audit-folder>` to refit audited
historical inputs into new candidate folders, comparing absolute and grid-residual
targets with corrected retirement labels. It checks original input/artifact hashes,
does not refit validation outcomes, and emits an inspected-race ledger. Pass that
ledger to simulation benchmarks with `--inspected-reports`, alongside earlier
benchmark reports. Reusing inspected historical holdouts is diagnostic only.

PRE forecasts can use optional `data/race_entries.csv` with columns `Year,Round,
Driver,Team,PublishedAtUtc,EntryListId,ExpectedEntrants`. Each list version must contain the complete
field at one timezone-aware publication time, with the independently declared
`ExpectedEntrants` repeated on every row and matching the selected version size; only versions available by the feature
cutoff are eligible. Historical PRE replay cutoffs cannot extend beyond the first
scheduled weekend session. Dated lists also supply the current team assignments.
With no eligible list, the previous race roster remains an
explicit assumption. Missing model features for an entrant fail closed. Frozen
rosters record the source, cutoff, version and input checksum where available.
There is no fabricated entry-list download or silent claim of verified coverage.

Validation artifacts from this change are under
`outputs/model_revision/20261010T214004Z`. No frozen forecasts, old models or
delivery receipts were rewritten. Existing executables require a separate rebuild.

The revised offline comparison completed 45 complete race/stage episodes over
20 cached races with 5,000 simulations and seeds 42, 123 and 777. All three candidates
remain disabled: there are zero fresh validation races after carrying forward the
saved-prediction and training inspection ledger. The previously seen Q diagnostic
subset contains 12 races:

| Variant | Finish MAE | Retirement Brier | Decision |
| --- | ---: | ---: | --- |
| Current formulas with corrected status semantics | 3.565 | 0.1244 | Baseline |
| All-cause retirement prior | 3.628 | 0.1110 | Better retirement scores; worse finish error |
| Single pace blend | 3.501 | 0.1244 | Diagnostic improvement; needs fresh validation |
| Q grid multiplier 3.3 | 3.351 | 0.1244 | Diagnostic improvement; needs fresh validation |

Corrected historical candidates were refit into six new folders, comparing both
finish targets. Grid-residual finish MAE still loses to qualifying order in each
2021/2024/2026 validation set. Corrected logistic retirement predictions also fail
to beat their training-rate prior baseline. These are inspected diagnostics, and
DNS/disqualification exclusions change some old/new metric denominators. The code
fix and successful training are not evidence that the candidates should go live.

Missing optional FastF1 weather properties no longer crash an offline comparison.
Neutral modifiers have an unknown rainfall flag, rather than asserting dry conditions;
benchmark reports preserve session-weather availability. This is an explicit missing
data assumption, not a weather forecast or a fitted delayed-start correction.
Post-race backtests and Discord retirement context also use the shared outcome
policy; missing retirement labels are excluded and reported, and unknown fantasy
retirement penalties are not scored as zero.

Keep the existing forecasting model live. The experimental `model.use_stint_pace` switch defaults to `false`; scheduled forecasts do not enable it. More simulations reduce sampling noise, not modelling bias.

An offline comparison on the available 2025/2026 cache used 5,000 simulations per model and episode, eight development races and six later held-out races. The matched-stint candidate's aggregate `finish MAE + top-10 Brier` loss was **3.4% worse** than the current model. It also lost the development comparison. It has not been promoted.

| Held-out stage | Races | Current finish MAE | Candidate finish MAE | Grid-order baseline MAE |
| --- | ---: | ---: | ---: | ---: |
| PRE | 6 | 3.669 | 3.668 | 3.258 |
| FP2 | 4 | 4.008 | 4.238 | 4.773 |
| Q | 5 | 3.383 | 3.556 | 2.727 |

The qualifying grid-order baseline outperforming the simulation is a useful warning: increasing model complexity is not yet justified. Next, investigate qualifying/grid blend weights on development data, then evaluate on newly reserved races. These held-out results have now been inspected and must not be reused as an untouched confirmation set after tuning.

The initial result is saved under `outputs/accuracy_benchmarks/20261003T053535159578Z`. Its report is schema v1; subsequent runs include source/input fingerprints and stronger coverage gates in schema v2. There were no cache-load failures in the initial run, but missing sessions and incomplete roster coverage caused evaluation skips.

## Implemented safeguards

- Historical training uses qualifying weather and race-control context, not the target race's conditions. Qualifying rank supplies the grid estimate rather than the final race-day grid.
- Training and validation are disjoint whole races, ordered chronologically. Small datasets fail explicitly rather than evaluating on the training rows.
- DNF classification no longer uses balanced class weights as if the resulting scores were population probabilities. Single-class training outcomes are handled safely.
- New benchmark compares both simulation variants with grid-order and recent-form baselines using identical complete-driver episodes. It reports finish MAE and win, podium and top-10 Brier scores, plus probability calibration bins.
- Development data selects the candidate; later race metrics are reported separately. The benchmark cannot itself enable a candidate or send Discord messages.

Existing trained historical artifacts are not retrained or automatically replaced by these code changes. Live automated forecasts currently have historical calibration disabled.

## Experimental matched-stint model

The legacy best-lap filter is preserved when the switch is off. The candidate separately retains eligible sustained dry runs that the fast-lap filter could discard. It requires at least five continuous laps, compares the same compound in 15-minute session windows with at least two drivers, and trims robust residual outliers. It compares fitted pace at a common tyre age.

Observed stint slopes combine tyre wear, fuel burn and track evolution; this is not an identified fuel correction or a pure degradation estimate. Unknown fuel caps confidence at 0.65. Sparse run evidence widens uncertainty rather than increasing DNF probability. Qualifying retains a separate qualifying signal, with available earlier practice used for sustained race pace.

Enable `"use_stint_pace": true` under `model` only for controlled shadow testing. The present evidence does not support enabling it in the scheduled config.

## Reproduce the benchmark

Run from the repository with its existing Python environment:

```powershell
python -m scripts.benchmark_accuracy --cache-dir data/cache --years 2025 2026 --n-sims 5000 --seed 42
```

FastF1 is placed in offline mode: no additional sessions are downloaded. The output folder is unique by default and an explicitly supplied existing folder is refused. Outputs include `race_metrics.csv`, `predictions.csv`, `summary.csv`, `calibration_bins.csv` and `report.json`.

The report records loaded-input hashes, source hashes, sampling settings, development/holdout race identities, skips and cache-load failures. The promotion gate requires development selection, at least six development and six held-out races at every requested forecast stage, at least 5% lower combined loss, and no aggregate Brier regression. Passing it is evidence for review, not automatic deployment or proof of calibration.

## Independent DNF and historical-pace experiments

The follow-up ablation tests two changes separately, against the unchanged live model:

- `decoupled_dnf_v1`: replace lap-quality-derived failure probabilities with the existing 0.045 prior before reliability blending. Pace confidence and uncertainty are unchanged; prior race status information still contributes downstream. This is not a newly calibrated all-cause failure rate.
- `normalised_history_v1`: convert each prior race's relative pace gap to a fraction of that session's fastest estimated true pace, then express it in target-lap seconds. Use current session evidence for the target reference; PRE uses prior same-event history or an explicit 90-second fallback. Other tyre, DNF and strategy parameters are unchanged.

Run from the main checkout:

```powershell
python -m scripts.benchmark_feature_ablations --cache-dir data/cache --years 2025 2026 --prior-report outputs/accuracy_benchmarks/20261003T053535159578Z/report.json --n-sims 5000
```

The final comparison is `outputs/feature_ablations/20261003T060541981274Z`, using seeds 42, 123 and 777. Earlier two passes are retained as development artifacts; the first omitted generic Retired outcomes from DNF scoring, and the second had not yet collapsed repeated seeds for calibration sample counts. Use the final report for decisions.

| Diagnostic stage | Races | Current finish MAE | DNF-only candidate | Normalised history |
| --- | ---: | ---: | ---: | ---: |
| PRE | 6 | 3.673 | 3.671 | 3.695 |
| FP2 | 4 | 4.016 | 4.019 | 4.082 |
| Q | 5 | 3.384 | 3.387 | 3.413 |

Both candidates meet their initial development selection rules, but neither is promoted. The DNF correction has negligible ranking impact and mixed diagnostic DNF scoring. Normalising historical pace worsens diagnostic finish error at every stage. There are no fresh validation episodes, and only two development FP2/Q races.

DNF scoring now treats a generic `Retired` status as a non-finish **without guessing the cause**. Other unknown statuses are excluded and counted explicitly. The final diagnostic episodes have complete DNF-label coverage; three driver outcomes in the development PRE sample remain unknown. Calibration bins average seed predictions per unique driver/race/stage before counting observations. Repeated simulations cannot inflate the validation sample size.

Reports save input/source fingerprints, stage coverage, baseline comparisons, target reference assumptions and promotion reasons. Earlier evaluated or skipped race outcomes remain inspected on later runs; reports in the same ablation output root are automatically included, and `--inspected-reports` can include reports stored elsewhere.

An important remaining issue is that mechanical reliability inference currently treats unclassified statuses as non-mechanical observations. Generic retirements establish a non-finish, but do not establish mechanical health or a failure cause. Resolve this with an independent unknown-status handling experiment and cause-aware data, rather than fitting failure rates to the small inspected sample.

## Limits

This reconstructs a pre-race feature cutoff from retrospectively cached feeds; it cannot prove that all cached values were published unchanged at that time. It uses the two most recent *cached* prior races, which may not be the two most recent real races, and current circuit defaults. PRE uses the latest historical roster and an estimated grid; Q uses qualifying order, without later penalties. Available stage samples are small and differ. Results do not establish generalisation across regulatory eras, a calibrated probability model, or an accuracy uplift.

## Qualifying/grid sensitivity experiment

The grid-weight benchmark varies one parameter only: the simulated grid-position time penalty. It does not change practice forecasts, qualifying race-pace weights, DNF rates or shared global configuration. `simulate_races(..., grid_loss_multiplier=...)` accepts a finite override from 0 to 50 for that call. Omitting it preserves the current 1.65 multiplier and existing predictions. The effective multiplier is included in the summary for provenance.

Run this experiment against the same report's fixed development partition:

```powershell
python -m scripts.benchmark_grid_weights --cache-dir data/cache --years 2025 2026 --prior-report outputs/accuracy_benchmarks/20261003T053535159578Z/report.json --n-sims 5000
```

The predefined sweep is 1.65, 3.3, 6.6 and 13.2, with seeds 42, 123 and 777. Seeds are averaged within each race, then races receive equal weight. Only development results select the multiplier; later races compare the locked choice against the current multiplier, without a further sweep. Previously inspected races are labelled `previously_seen_diagnostic`, not fresh validation. Newly cached qualifying races later than all inspected races are eligible for `fresh_validation`.

The initial experiment at `outputs/grid_weight_benchmarks/20261003T054830318412Z` selected **13.2** on the two available development qualifying races. That is the search boundary, not evidence that 13.2 is a stable optimum. On five previously inspected diagnostic races:

| Metric | Current 1.65 | Candidate 13.2 |
| --- | ---: | ---: |
| Finish MAE | 3.384 | 2.720 |
| Win Brier | 0.0410 | 0.0282 |
| Podium Brier | 0.0662 | 0.0756 |
| Top-10 Brier | 0.1319 | 0.1027 |
| MAE + top-10 Brier | 3.516 | 2.823 |

Lower is better for every metric. Finish MAE improved about 19.6%, but podium Brier worsened about 14.2%. Development top-10 Brier also worsened at the selected weight. The simple grid-order diagnostic baseline had MAE 2.727, essentially matching the candidate: most of its apparent benefit is greater grid trust, not a demonstrated improvement in physical race modelling.

At the current weight, the grid penalty spans about 13-30 seconds across these fields, versus roughly 35-85 seconds for the race-pace contribution. This supports investigating excessive trust in historical pace, but does not establish the correct physical penalty. A larger grid penalty can suppress genuine overtaking and recovery potential.

There were **zero fresh validation qualifying races**, so live parameters remain unchanged. Promotion requires at least six development and six fresh qualifying races, at least 5% lower combined loss, and no win/podium/top-10 Brier regression. The script writes seed-level metrics, race-level metrics, predictions, simple-grid comparisons, input sensitivity and a report with input/source hashes. Repeated seeds quantify simulation sampling sensitivity, not certainty about performance on future races. Rerunning this experiment with later race data must keep prior inspected races excluded from fresh validation.
