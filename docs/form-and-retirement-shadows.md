# Stage-specific form and retirement shadows, 24 October 2026

The form adjustment, its interaction with degradation, and a separate simple
retirement prior are implemented and compared through the real simulator.
**Live predictor defaults are unchanged.** Historical screening supports new
PRE/FP2 research captures, not production promotion. Q candidates remain parked.

## What the form candidate does

`src/form_adjustment.py` builds past-only driver/team form and matched earlier
race-pace features. It fits fixed Ridge alpha 100 models on strictly earlier
completed races. PRE/FP2 use no target Q features. Q fits a change from official
qualifying percentile, retaining that anchor at inference. Six earlier eligible
races and 60 rows are required; insufficient history is recorded explicitly.

The implied finishing percentile is mapped onto the current field's sorted
race-pace distribution. It blends 35% at PRE, 25% at FP2 and 15% at Q into the
existing race-pace scores. These are declared experimental weights, not fitted
optima. The conversion is a heuristic, not an identified physical pace model.
Outcome-based form can also contain earlier retirement/strategy effects.

Actual grid positions remain facts and are never replaced by the form estimate.
The same pace change is applied to long-run pace so their difference is
preserved; this does not add another wear penalty. The simulator then generates
the coherent position distributions, joint race orders and outcome probabilities.
Zero form weight exactly reproduces the established simulator. The candidate is
available to research code only, not selected by normal run configurations.

History is snapshotted from verified archived Q/R tables. Three malformed R
classifications are excluded instead of assigning missing/duplicate ranks:
2021 Abu Dhabi, 2022 Saudi Arabia and 2023 Singapore. The packet contains 127
usable race histories. Other archive-load exclusions and skipped episodes remain
in the benchmark report. Historical feeds may contain retrospective revisions;
original publication times are not attested.

## Matched simulator experiment

Five arms use identical complete-driver episodes, simulation settings and seeds:
established, form only, single degradation only, form plus degradation, and
simple retirement prior only. Each uses 2,000 sims per seed, seeds 42/123/777.
There are 290 complete race/stage episodes across development and later data.
Models refit using only earlier race outcomes; settings are never searched.
Development is 2021–2024; 2025–2026 is previously inspected diagnostic evidence.
There are **zero fresh scored validation races** in this replay.

| Later diagnostic stage | Matched races | Established finish MAE | Degradation only | Form + degradation | Combined loss reduction vs established |
| --- | ---: | ---: | ---: | ---: | ---: |
| PRE | 30 | 4.274 | 4.042 | **3.982** | **6.95%** |
| FP2 | 26 | 4.228 | 3.866 | **3.832** | **9.48%** |
| Q | 35 | 3.773 | 3.506 | **3.443** | **8.79%** |

Loss is finish MAE + top-10 Brier. Combined PRE/FP2 losses improve on development
data too, with no later win/podium/top-10/DNF Brier regression against established.
RPS, log score and head-to-head scores are retained alongside the existing scores.

Most benefit is from degradation correction. The **incremental** loss reduction
from adding form to degradation is 1.54% PRE and 0.93% FP2. Their paired
race-bootstrap loss-difference intervals are [−0.111, −0.023] and [−0.083, +0.001],
respectively. The FP2 interval still includes no incremental form benefit.
These inspected-history intervals are exploratory and not multiplicity-adjusted.

Form alone fails development selection at PRE/FP2 and does not meet the 5% loss
rule at any stage. This is a useful limit: the earlier standalone factor study's
apparent gains did not transfer directly to the simulation without the wear fix.

Q qualifying-order MAE is **3.304**, beating the combined candidate's 3.443.
Therefore no Q form/degradation arm is registered for fresh collection. This
decision was retained even though the candidate improves on the established Q
simulation. Different simulation budgets explain small differences from the
earlier 5,000-sim degradation report; comparisons within this experiment match.

## Separate retirement experiment

The all-cause prior is Beta(1,9), with an equal mixture of earlier same-season
driver and current-team rates. Unknown labels do not imply mechanical health;
generic `Retired` is a known non-finish without an invented cause. Target/future
outcomes are excluded, and team history resets by season. Existing engine risk
clipping and weather modifiers remain in effect. Raw/effective inputs and counts
are saved for review. No manufacturer-level mechanical model is inferred.

| Stage | Established DNF Brier | New prior DNF Brier | Reduction | Diagnostic decision |
| --- | ---: | ---: | ---: | --- |
| PRE | 0.12910 | **0.11623** | **9.96%** | Collect separately |
| FP2 | 0.12524 | **0.11170** | **10.81%** | Park: small podium Brier regression |
| Q | 0.13054 | **0.11653** | **10.73%** | Park: small win Brier regression |

The prior is not combined with the form/wear candidate. Its predeclared research
screen requires at least 2% DNF Brier improvement, no more than 1% combined-loss
regression, no win/podium/top-10 Brier regression and development selection. This
screen is not a replacement for existing live promotion requirements. The small
FP2/Q regressions may involve sampling uncertainty, but were not silently waived.
Probability calibration bins average seeds before counting unique observations.

## Independent prospective collection

The existing active four-arm trial suite remains byte-for-byte unchanged and
continues independently. New local configuration `config/form_shadow.json` is
ignored by Git and enables an additional **shadow-only** source-run hook:

- PRE: established control, degradation-only control, form + degradation, and
  the separate retirement prior.
- FP2: established control, degradation-only control, form + degradation.
- Q and unsupported stages: parked; no new candidate substituted.

Form choice is selected on development loss; later diagnostic criteria can
reject it. The degradation-only control is retained to isolate the extra form
contribution on fresh races, rather than crediting form with the wear fix's gain.

Final cohort: `outputs/form_shadow/suites/20261024T161749074356Z_0d08ff5e/suite.json`,
SHA-256 `34e9f1153a1071ee3204b9ad0e59ef9a2b77ed0e05b962ca192222b9479c8d19`.
The prior development capture and configuration backup are retained, but are not
pooled with this cohort. Code/input changes require a new cohort, never an
in-place re-pin. The original four-arm suite remains SHA-256
`b07f85eeaaead705d25bd53af7769b64d3f6aff52ecaf6c588184ad4313a75f3`.

A fresh US FP2 capture completed all three registered arms, with no upload. The
source forecast was independently frozen during the earlier recovery work; it
was not rewritten. This is a new forecast at capture time, with source-feature
and history cutoffs recorded separately. The scheduled runner's reused FP2
source was also checked: it reuses this capture without duplicating it. Q form
captures additionally require a frozen official-Q feature contract if a future
cohort enables them; an estimated or later race-day grid is not a substitute.

The existing hourly task itself was not changed or manually triggered. Its
source entry point now calls the optional hook after the existing forecast and
delivery work. The hook is disabled without its local configuration, never
posts, never downloads results, and uses the existing workspace lock. Optional
arm failures are recorded without losing the control or other successful arms.
New capture failures do not prevent completed scoring from draining. Optional
research failures appear as automation warnings rather than failing live delivery.

Completed official result jobs are reused at least eight hours after race start.
Frozen source, suite, features, joint samples and result hashes are checked.
Scores are write-once; unknown DNF labels are excluded and counted. Seeds are
collapsed within a unique race/stage, never counted as independent races. The
comparison report rejects duplicate captures and retains the existing fresh
review gates. No report or scheduler run activates a model.

## Commands and evidence

Run in the main checkout with the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_form_adjustment --workspace "$env:LOCALAPPDATA\RaceWorkbench" --output-dir outputs/feature_ablations/NEW_FORM_BENCHMARK
.\.venv\Scripts\python.exe -m scripts.form_shadow --register outputs/feature_ablations/NEW_FORM_BENCHMARK
.\.venv\Scripts\python.exe -m scripts.form_shadow --verify-only
.\.venv\Scripts\python.exe -m scripts.form_shadow --capture "outputs/app_runs/FORECAST_ID"
.\.venv\Scripts\python.exe -m scripts.form_shadow --score
.\.venv\Scripts\python.exe -m scripts.report_form_shadows
```

Benchmark output folders must be new. Registration requires an unchanged,
inactive benchmark with stages passing screening. It snapshots history/training
inputs, carries forward inspected-race ledgers and backs up an existing research
configuration. No credentials or service settings are changed.

Local benchmark evidence is under
`outputs/feature_ablations/20261024-form-retirement-shadow-r2`: protocol,
history/training CSVs, fitted models, predictions, calibration bins, race/seed
scores, source/input fingerprints, screening decisions and paired diagnostics.
The benchmark report SHA-256 is
`236b0fe030156f2864596d3aa9a8c88e247a2ce6572365607284ad493805a7f7`.
The initial failed packet-build attempt is retained as diagnostic evidence.
Prospective captures and comparison reports are under `outputs/form_shadow`.
There are no fresh scored results yet; the first captured race has not finished.

Verification includes target/future leakage tests, official-Q enforcement,
zero-weight legacy reproduction, coherent simulated probabilities, unknown
retirement semantics, immutable capture reuse, official-result scoring,
failure isolation and rejection of duplicate race/stage observations. Full
regression results and preservation checks are recorded with the local evidence:
**841 Python tests and six JavaScript tests passed**, with five existing Python
deprecation warnings. Both the original and independent shadow suites verify.
No dependency installation, executable rebuild or live parameter promotion was
performed.
