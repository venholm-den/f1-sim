# Training from downloaded historical sessions

Experimental practice and reliability inputs are now available through the
**Include practice long runs and recent reliability** checkbox. The default
qualifying-only path below remains available. See
[Prediction data enrichment](prediction-data-enrichment.md) for collection,
timestamp gates, coverage and the separate FIA/weather/strategy datasets.

Open **Historical Data**, select detailed seasons (2018 onwards), and download
**Qualifying (Q)** and **Race (R)**. Other sessions and telemetry are optional
for your archive; this trainer does not use them. Classifications-only downloads
from 1950 onwards do not contain the qualifying timing needed by these models.

Open **Model Training**, choose saved seasons, and click **Train candidate**.
The page shows matched race coverage. At least three matched races are required;
this minimum enables the software, not a credible accuracy claim. Download many
more races before evaluating a candidate. Missing pairs are listed in the report.

Training runs in a cancellable local worker. The app shares one worker between
downloads, training and Simulation Centre jobs. Race Setup cannot run concurrently.
Stopping training keeps its diagnostic files but does not expose a ready candidate.
You can train again; every run uses a new folder.

The trainer fits a Ridge **change from qualifying order** model and a logistic
retirement model, with a constant prior for single-class retirement samples.
The qualifying anchor is restored at inference. Validation also exports a unique
finishing order from predicted scores, with deterministic driver-code tie breaks;
that order is reported separately from mean-finish error and covers the modelled
qualifying cohort. It is not evidence of complete race-field coverage; simulation
promotion still requires the full-field benchmark gate.
DNF means a recognised retirement outcome, not an inferred mechanical failure cause.
Finished, Lapped and +N Lap(s) are finishers. Generic Retired is a non-finish with
unspecified cause. DNS and disqualification are excluded from both fitting targets;
other unknown retirement labels are excluded from retirement fitting/scoring and
counted explicitly, while usable finish positions can still train the finish model.
Drivers without usable qualifying timing or finish positions are excluded and
counted. Duplicate outcomes and empty status labels fail rather than creating
misleading training rows.

Validation holds out the latest selected season. For a single selected season,
the last approximately 25% of its races are held out. Entire race fields remain
in one partition, ordered by season and round. The models are fitted only on
the earlier partition; they are not refitted on inspected validation outcomes.
Qualifying weather/control context may be used. Race weather/control, final
race-day grid penalties, sprint outcomes and race laps are excluded from predictors.

Review **Finish MAE** and **DNF Brier** against the qualifying-order and
training-DNF-rate baselines. Lower is better. The page also shows finish RMSE,
driver/race coverage and the exact training/validation races.

**Open run folder** opens `outputs/app_runs/<run-id>` in your chosen workspace:

- `candidate/`: both joblib models, feature table, metrics and held-out predictions.
- `training_result.json`: metrics, source hashes, skipped races and artifact hashes.
- `training_selection.json`: pinned archive version/provenance records.
- `training_inputs/`: checksummed source copies, assembled CSVs and snapshot manifest.
- `run.log` and `training_progress.json`: progress and diagnostics.

Archive files are checked against the pinned version's hashes before fitting.
The app verifies candidate hashes when showing completed results. A repaired or
redownloaded session can advance its archive pointer without changing a run's
pinned older version. Existing active artifacts under `data/models` are preserved.

Training never activates a candidate or changes scheduled forecasts. A model
directory can be inspected independently in its validation exports. Historical
calibration now defaults to off. The live loader refuses candidates without both
`promotion_eligible: true` and `activated: true` in their metrics; new training jobs
always save both as false. Old artifacts without promotion metadata are also skipped.
Changing a model directory or enabling the old calibration flag does not activate
an unreviewed candidate. See [accuracy-improvements.md](accuracy-improvements.md)
for the independent validation required before a promotion decision. These local
metadata flags record a reviewed decision; they are not tamper-proof certification.

These are retrospective chronological holdouts, not proof that cached feeds
were unchanged at prediction time. Repeatedly tuning against the same holdout
consumes its independence. Different seasons may span different regulations;
more downloaded rows alone do not establish improved accuracy. Compare with the
live simulation on fresh reserved races before making a deployment decision.
