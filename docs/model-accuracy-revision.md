# Qualifying, pace and retirement revision

Implemented in the main source checkout on 11 October 2026. Active forecast
configuration remains on the legacy simulation pending promotion gates. Frozen
forecasts, active model artifacts and delivery receipts are preserved. Existing
packaged executables have not been rebuilt.

## Official qualifying anchor

`src/qualifying_features.py` supplies the shared `official_q_classification_v1`
contract for historical training and current post-Q inference. `q_rank` comes
from Q result `Position`, rather than ranking fastest laps across Q1/Q2/Q3.
Timing predictors remain fastest valid laps/sectors over the whole Q session;
these are not estimates corrected for changing track conditions.

Training snapshots now include Q classifications alongside Q laps and R outcomes.
Incomplete Q classifications cannot silently become synthetic ranks. Events
missing Q ranks for their race entrants are excluded from fitting; missing timing
is imputed without discarding an entrant's official rank. Joins use event and
driver independently of team-name aliases. New candidates record training source
hashes and remain inactive.

Inference consumes these same raw Q fields and uses the post-Q anchor before
Sunday penalties; the separate simulation grid still incorporates available
penalties. Calibration fails closed if the feature contract or complete field is
missing, or artifacts were trained under the previous contract.

## Selectable experiments

Both settings below default to `legacy`. Existing active configs are unchanged.

| Model setting | Candidate value | Effect |
| --- | --- | --- |
| `pace_blend` | `single_pace_blend_v1` | Mix raw capped current and historical gaps once, multiplying the stage race weight by quality once |
| `retirement_model` | `all_cause_dnf_v2` | Replace lap-quality-derived retirement risk with prior outcome estimates |
| `retirement_model` | `retirement_progress_v1` | Same outcome risk, plus conditional completed-distance classification |
| `retirement_history_races` | 30 by default, 1–100 | Retirement lookback independent of the shorter pace baseline |

Single-pass pace records current/history weights summing to one, uses explicit
fallbacks for missing evidence, preserves the tyre/consistency offset and updates
projected lap time. Its final race-pace input does not depend on the earlier
`model_pace` blend. Qualifying, strategy and uncertainty retain their existing
definitions. Matched-stint and single-pass candidates are rejected when combined.
The source pipeline, offline replay and prospective pace trials share the same
single-pass function.

Retirement probability uses explicit population/team/driver/circuit shrinkage
assumptions. Unknown, DNS and disqualified statuses are not known healthy
finishes; generic retirement retains an unspecified cause. Only distinct earlier
races are accepted. Additional history loads only when the candidate is selected
and can require extra FastF1 downloads in source runs. Offline replay uses cache.

The distance candidate fits a recency-weighted ten-bin histogram to known earlier
retirements, with ten uniform pseudo-observations and a uniform fallback without
distance evidence. Classification `Laps` is preferred; otherwise recorded timed
laps are used, with a conservative fallback when lap-time evidence is absent.
Sampling is conditional on retirement and uses an independent random stream so
paired pace and retirement-occurrence draws are preserved.

Ordering uses completed laps and estimated crossing time. The 90% winner-distance
threshold determines classification and points eligibility, including late
retirements, following
[FIA Sporting Regulations Issue 09, B2.5.5](https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_b_sporting_-_iss_09_-_2026-10-01.pdf).
This is still an aggregate approximation: surviving cars complete full distance;
lapping, correlated incidents, lap-by-lap traffic, shortened-race points and
cause-specific retirement timing are not simulated. The assumptions need
validation; implementation alone does not establish improved accuracy.

Raw results expose completed laps, classification eligibility and version.
Summary provenance includes pace weights and retirement model/history versions.
`points_chance` keeps its existing top-ten meaning for old trials;
`points_scoring_chance` represents actual simulated points.

## Repeatable comparisons

From `C:\code_project\f1-sim`, using the existing environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.benchmark_feature_ablations `
  --prior-report outputs/accuracy_benchmarks/20261003T053535159578Z/report.json `
  --inspected-reports outputs/model_revision/20261010T214004Z/simulation_benchmark_v2/report.json `
  --variants legacy single_pace_blend_v1 all_cause_dnf_v2 retirement_progress_v1 single_pace_retirement_v1 `
  --n-baseline-races 2 --retirement-history-races 30 `
  --n-sims 3000 --seeds 42 123 777
```

Use `--n-baseline-races 5` to test the manual run's usual lookback. Replay records
both history lengths and uses the selected pace history for its recent-form
comparator. Separate ablations isolate pace, occurrence and distance; the combined
candidate is an additional declared diagnostic. Source hashes are captured before
evaluation and checked before saving. A changing checkout invalidates the run.

Already inspected outcomes remain diagnostics. Multiple seeds are not additional
independent races. Each stage still needs sufficient fresh races, development
selection, at least 5% lower combined loss and no outcome Brier regression before
promotion review. Retirement changes must also improve DNF Brier. Nothing
auto-activates.

New prospective suites pin the expanded source set and can carry new inspection
ledgers forward with `scripts.prediction_trials --register --inspected-reports`.
Old suites/captures remain immutable; old forecasts are not
reinterpreted with changed simulation code. The existing prospective suite covers
pace/grid/stage-blend experiments; retirement candidates currently have offline
replay support rather than an automatic prospective arm.

Results and preserved pre-edit source are in
`outputs/model_revision/20261011T032552Z_accuracy`; `review.md` records the measured
comparisons and promotion decisions.
