# Prospective practice collection and model comparisons

The [23 October grid-influence comparison](grid-influence.md) adds the inactive
`grid_influence` arm with separately selected PRE/FP2/Q difficulty mappings.
It uses the existing simulation control's seeds and sample budget and freezes
the exact mapped input. Historical results do not pass promotion gates.

The [SC/VSC and tyre follow-up](simulation-gap-tests.md) adds
`agent_neutralisation_v1` against `agent_laps_v1` and `pit_inventory_v1` against
`pit_scenarios_v1`. New snapshots freeze the tyre inputs; the expanded history
retains race-control labels. Missing inputs skip the affected arm. Earlier
suite versions and forecasts remain immutable.

The existing hourly PC task now collects available current-weekend practice and attempts a versioned shadow comparison after a new frozen forecast and when it reuses an existing forecast. Collection also runs at stages outside the blend's PRE/FP2/Q support and uses the current calendar context even if an older Q forecast is reused. Trial features remain bounded by their original source forecast cutoff. Live probabilities, model settings, old forecasts and Discord delivery plans are unchanged. Local opt-in configuration is `config/prediction_trials.json`; the checked-in example is disabled.

## Predeclared comparisons

| Output | Definition |
| --- | --- |
| `simulation` | Established simulation, rerun with the same inputs and seeds as the experimental simulation variants |
| `stage_blend` | Existing fitted PRE/FP2/Q component weights, with newly collected eligible FP2 evidence replacing the target practice archive |
| `stronger_grid` | Grid loss multiplier 3.3 for Q only; other inputs unchanged. PRE/FP2 are identical controls and are excluded from stronger-grid improvement summaries |
| `single_pace` | Existing `single_pace_blend_v1`, applied once to saved raw current/history gaps; retirement, strategy and grid inputs unchanged |
| `grid_influence` | Pinned stage-specific difficulty mapping selected only on development races; currently active difficulty times 1.25, capped at 0.95; same simulation control budget |
| `frozen_simulation` | Original saved probabilities, retained as a secondary reference |
| `qualifying_order` | Complete qualifying classification baseline, when available |
| `candidate_control` | Established simulation at the new candidates' matching 1,000-per-seed budget |
| `pit_scenarios_v1` | Explicit assumed one/two-stop plans; dry conditions only |
| `survival_dnf_v1` | Competing retirement hazards and completed-lap classification, with pace unchanged |
| `qualifying_partial_pooling_v1` | Bayesian Q-to-race pace with posterior uncertainty; Q stage only |
| `agent_laps_v1` | Independent car-agent interactions, fuel, tyres, pit plans and blue flags; dry only, one-second steps |

The original simulation variants use 5,000 simulations for each of seeds 42, 123 and 777; seed predictions are averaged before scoring. Whole races, rather than drivers, simulation seeds or repeated scheduler checks, are the independent evaluation units. Candidates are independent changes, not a combined model.

The four new arms and `candidate_control` each use **1,000 simulations for each of seeds 42, 123 and 777**. Their paired comparisons use this control, so sampling budgets match. The agent engine typically adds about a minute for three seeds on this PC; actual time varies by circuit and field. Main forecast Discord delivery occurs before the new candidate runs. Each arm records completion or an explicit skip reason. Wet agent/pit runs, missing history and missing official Q features are never silently replaced with another model. A failed arm cannot prevent other arms from completing. A committed trial, including its skip records, is immutable and is reused on subsequent hourly checks.

The currently enabled suite has a checksum-pinned snapshot of 40 cached Q/race pairs. Survival uses the most recent 30 eligible earlier races; Bayesian pace refits its declared posterior for the target using eligible earlier Q/dry-race pairs with known rain observations. The archive is **fixed for the suite**, as are its priors and other settings: it does not automatically ingest new outcomes or tune hyperparameters. A future archive update requires a new suite and a carried-forward inspection ledger. Future/target outcomes are filtered before fitting, and the history packet must predate trial start. Its declared history cutoff is separate from the original feature cutoff: a reused forecast can have older current-weekend features than the newly registered historical archive. Both cutoffs are exported with each candidate; these are forecasts made at trial time, never backdated to the original forecast. The portable packet stores original table values and timedelta types, without loading a pickle during scheduled runs.

Successful arms freeze their exact feature CSV, resolved simulation options (including agent parameters and pit plans), seeds and fitted posterior. All files join the capture checksum manifest and are verified again when scoring. These are PRE/FP2/Q trials; other session stages continue collection but do not silently substitute into this protocol. Race-window weather updates continue their existing separate informational capture and are not an additional scored model arm here.

The fitted stage weights are copied and pinned, not refitted. Its qualifying component continues to mean Q classification, even when the simulation uses a later FIA grid. Practice inputs remain FP2 only because that is the component on which the existing weights were fitted. FP1 and FP3 are collected and exported, without silently substituting them for FP2. Sparse FP2 coverage uses the existing 60% availability gate and explicit simulation fallback. Introducing another practice component requires a separate training experiment and suite.

## Automatic collection

Only practice sessions listed as completed in the source forecast are requested. PRE requests no practice. FastF1 must provide a terminal session status, an actual UTC timing origin, matching event/physical circuit/layout, accurate laps and lap-end times before the source cutoff. Telemetry is loaded into the ordinary cache to establish FastF1's UTC origin; the trial packet stores lap evidence and normalized features, not a duplicate full telemetry archive.

Clean dry sustained laps are compared by compound, tyre age and session-time bucket using the existing matched-stint extractor. Yellow/red/SC/VSC laps, deleted laps and pit crossings are excluded. Practice after scheduled qualifying is retained as raw evidence but excluded from the existing trained component, covering older sprint formats. Unknown fuel loads remain unknown. UTC timing origins, completion times, qualifying schedule bounds, clean counts and matched-driver counts are recorded.

Packets under `outputs/practice_collection` are append-only and content-hashed. Successful packets for the same cutoff/parser are reused. Unavailable or incomplete sessions defer the trial and retry on the next scheduled check; failed evidence is retained. No capture becomes prospective after race start. This is collection for shadow experiments; it does not enable the live matched-stint switch or automatically retrain an archive/model.

## Provenance and scoring

Each registered suite pins the ensemble, its outcome/practice training archives, the previously inspected race ledger, trial assumptions and participating source hashes. A source change requires registering a new suite. A prospective target must be later than all races in that inspection ledger and stage training/calibration history.

New automated forecasts freeze `simulation_inputs.json`, containing the exact weather modifiers and overtaking input. Older saved inputs are accepted only when their identity/timestamps are consistent and replay reproduces the frozen finish/win/podium/top-10/DNF output within numerical round-trip tolerance. Unsupported inputs fail closed. The source forecast remains unchanged.

The first complete trial per suite/race/stage is immutable; retries reuse it. Interrupted writes are retained and a later attempt uses a separate folder. Trial creation is after registration and data capture, and before race start. Local clocks are unattested.

After the existing post-race process has saved complete official results, trial scoring waits at least eight hours after scheduled race start and reports finish MAE, win Brier, podium Brier, top-10 Brier and DNF Brier together. Scoring never downloads results or posts anything. It rechecks prediction, suite, practice, source forecast and official-result hashes. Scores are write-once.

The report groups cohorts by suite and stage and compares candidates on identical races. It reports paired metric differences and whole-race bootstrap finish-error intervals once two races are available. At least six fresh races per stage, at least 5% lower paired threshold RPS (the mean of win, podium and top-10 Brier), no finish MAE or win/podium/top-10/DNF Brier regression, and Q finish error beating qualifying order are required for review. Threshold RPS is derived when the report is built, so existing score files and suites are not rewritten; suites registered before 24 October 2026 record the earlier loss gate in their manifest, and the report applies the current rule to them. The paired loss is still reported. No test, report or scheduler run activates a model.

## Commands

Register the existing ensemble and enable the original local three-way experiment, preserving any previous configuration in an output backup:

```powershell
.\.venv\Scripts\python.exe -m scripts.prediction_trials --register --latest --score
```

Register the expanded protocol with an existing portable history snapshot (copies it into a new immutable suite). Carry all previously inspected outcomes forward:

```powershell
.\.venv\Scripts\python.exe -m scripts.prediction_trials --register --extended-models --history-packet <candidate_history.json.gz> --inspected-reports <prior-suite.json>
```

The active local configuration points to the original three comparisons plus
the grid-influence arm; the optional expanded agent/pit/survival arms are not
enabled by this registration. No scheduled-task change is needed. `--latest`
never manufactures prospective trials for previously inspected or already-started races.

Subsequent local capture/scoring/report, without Discord:

```powershell
.\.venv\Scripts\python.exe -m scripts.prediction_trials --latest --score
```

Scoring/report only:

```powershell
.\.venv\Scripts\python.exe -m scripts.prediction_trials --score
```

The normal task invokes these services automatically; no additional scheduled task or Codex automation is needed. `scripts.auto_forecast --check-only` makes no trial or practice writes. Reports are versioned under `outputs/prediction_trials/reports` and focus on the currently enabled suite. Earlier protocol versions and captures remain preserved and are never pooled to inflate sample size. Existing desktop binaries require a separate rebuild to include changed source; PC scheduled source runs use it immediately.
