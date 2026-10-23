# Stage-specific prediction blends

The follow-up [prospective prediction trials](prospective-prediction-trials.md) adds automatic current-weekend practice snapshots and a separate pinned comparison of the existing stage weights, Q grid multiplier 3.3 and single pace blend. It does not change this original archive-based shadow service or activate the live model.

`stage_ensemble_v1` is an experimental, inactive candidate. It learns a small
set of weights for PRE, FP2 and Q separately. It does not replace the live model,
change Discord messages, refit retirement risk, or edit frozen forecasts.

## Inputs and safeguards

The components are the established simulation, Q classification, recent classified
finishes, and timestamp-filtered FP2 matched long runs from the prediction-data
exporter. Recent form uses up to five earlier archived races in the same season.
No qualifying component is available at PRE/FP2. PRE cannot use current practice.
Q uses qualifying classification, excluding subsequently published penalties.
It requires a complete actual classification; even one estimated grid entry
disables that component for the whole-field blend. Observed coverage is still
reported so this fallback cannot be mistaken for an absence of all Q data.
Practice requires at least 60% field coverage; absent drivers use median pace.
Missing components fall back to the simulation. Recent form more than three rounds
old is unavailable. Sparse components need six usable earlier race episodes to
receive a learned weight.

Qualifying/recent/practice components simulate whole finishing orders with three
positions of Gaussian ranking noise and the original simulation's retirement
probabilities. These are declared assumptions, not fitted lap-time or fuel effects.
Weights are nonnegative and sum to one, with a penalty towards the established
simulation. The training objective is finish MAE plus top-10 Brier plus
`0.10 * sum((weight-prior)^2)`, averaging whole races equally. Fields retain
win=100%, podium=300%, top-10=1000% and nested event probabilities.

Monte Carlo seeds are averaged per driver/race/stage before fitting. Every target
uses only earlier same-stage race outcomes. A second, experimental calibration
step softens the complete field distribution with at most 35% uniform mass,
fitted on at least six earlier *out-of-sample* learned blends. It minimises mean
win/podium/top-10 Brier plus `0.01 * uniform_mass^2`. Warm-up fallback predictions
are excluded from its training. This adjustment is a comparison output only:
the initial diagnostic found it worsened subsequent results.

## Reproduce the diagnostic

From `C:\code_project\f1-sim`:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_stage_ensemble `
  --source-report outputs/model_revision/20261010T214004Z/simulation_benchmark_v2/report.json `
  --dataset outputs/prediction_data/20261010-enrichment-complete
```

The source report's prediction checksum must match. Saved target classifications
must match the supplied outcome archive with complete driver coverage. Each run
creates a new directory and an inactive `candidate.json`; it cannot overwrite an
earlier experiment. Outputs include the chronological fits, component coverage,
paired race metrics, whole-race bootstrap intervals, reliability bins, input/source
hashes and a standalone `report.html`. All source races are marked previously
inspected; this replay supplies **zero fresh validation races**.

The first replay contains 45 race/stage episodes. After six earlier training races:

| Stage | Evaluated races | Simulation finish MAE | Blend finish MAE |
| --- | ---: | ---: | ---: |
| PRE | 12 | 4.185 | 3.936 |
| FP2 | 1 | 4.372 | 3.730 |
| Q | 14 | 3.827 | 3.467 |

On the 12 paired Q races with a complete usable qualifying classification, blend
MAE is 3.403 versus qualifying-order MAE 3.432. This small difference is uncertain.
The Q model fitted for the next race gives approximately 34% simulation, 61%
qualifying, 4% recent form and 0% practice. PRE's podium Brier regresses, and FP2
has only one evaluated trained forecast. These findings do not permit activation.

## Prospective shadow collection

`src/app_services/ensemble_shadow.py` is called after a new automated forecast is
frozen and when an existing forecast is reused. An optional local
`config/stage_ensemble_shadow.json` pins an inactive candidate and its checksum:

```json
{
  "enabled": true,
  "candidate_path": "outputs/stage_ensemble/EXPERIMENT/candidate.json",
  "candidate_sha256": "COPY_THE_CANDIDATE_SHA256",
  "results_path": "outputs/prediction_data/DATASET/retirement_records.csv",
  "practice_path": "outputs/prediction_data/DATASET/practice_features.csv"
}
```

The checked-in example is disabled. This PC's local pointer can enable collection;
`enabled` controls **shadow capture**, not model activation. Source/feature hashes
must still match training provenance. A source change requires a new versioned
candidate. Training/calibration race keys must precede the target race. A capture
must occur before the race starts and cannot be backdated before either its
candidate or source forecast existed. Unsupported stages return an explicit skip.

Outputs live separately under `outputs/stage_ensemble_shadow`, with a hash-pinned
manifest and separate simulation, learned blend, calibration comparison and
qualifying-order tables. An existing capture is verified and reused. Experimental
failures are reported without interrupting normal forecast creation or delivery.
No ensemble table is automatically sent to Discord.

Current practice will be unavailable when the pinned enrichment archive lacks the
new weekend; the manifest records that fallback. Updating the archive requires
a new benchmark/candidate and pointer. No live current-weekend practice collector
or automatic retraining is claimed by this feature.

The source `scripts.auto_forecast` also drains shadow scoring after normal work,
including `--post-race-only`. It reuses completed official scoring jobs, verifies
their source snapshots and complete classifications, and waits at least eight
hours after scheduled race start. It never downloads results or posts messages.
Completed shadow scores are write-once. `--check-only` performs no shadow writes.
Packaged executables built before this change do not contain the new service;
the PC's scheduled source automation does.

Live promotion remains a separate review: at least six fresh race forecasts per
stage, at least 5% lower finish-MAE-plus-top10-Brier loss than the established
simulation, no win/podium/top10/DNF Brier regression, and Q finish error beating
qualifying order on the identical cohort. Local timestamps are unattested and
are not proof of an externally submitted forecast. More iterations on the same
historical results cannot satisfy the fresh-evidence requirement.
