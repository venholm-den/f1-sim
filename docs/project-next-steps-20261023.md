# Follow-up: 23 October 2026

## Implemented

- Circuit outlines can use earlier downloaded geometry with matching physical
  circuit and layout IDs. Same-weekend telemetry takes priority. References name
  their source year/session, omit current lap/sector records and do not change
  forecast inputs. Later seasons cannot supply earlier targets.
- OpenF1 session queries use the target race's start window. PRE forecasts without
  verified classifications make no request. Legacy snapshots without circuit IDs
  are explicitly withheld from checks. HTTP 401/403 becomes an optional access
  warning with bounded retries. F1 TV does not authenticate OpenF1. A separately
  supplied local OPENF1_TOKEN is supported; none was provisioned.
- Settings displays forecast, weekend and post-race Discord receipts and times.
  The main strip shows the latest delivery. Sent means Discord accepted it, not
  that it was read. Missing receipts remain unknown; uncertain deliveries require
  review. No old report was manually resent.
- A malformed desktop HTTP SQLite cache is retained intact. An opt-in
  data/cache/http_backend.json selects a separate replacement HTTP database while
  retaining processed datasets. Repairs used an isolated cache. Nothing was deleted.

## Archive and training coverage

Missing R sessions were repaired for Belgium/Abu Dhabi 2021, Saudi Arabia 2022 and
Singapore 2023. Archive-only handling retains nonparticipating withdrawn/ill entrants
with their original statuses and missing ranks; live completeness checks stay strict.
Belgium 2021 is retained as an aborted/finalised classification and excluded from
normal race training. Eligible Q/R pairs increased from 127 to 130.

| Season | Eligible pairs | Completed calendar races |
| --- | ---: | ---: |
| 2021 | 21 | 22 |
| 2022 | 22 | 22 |
| 2023 | 22 | 22 |
| 2024 | 24 | 24 |
| 2025 | 24 | 24 |
| 2026 to audit date | 17 | 17 |

The new inactive candidate fitted 121 races: 106 training races/2,095 rows and
15 validation races/325 rows. Nine paired races have missing or duplicate Q ranks
and remain excluded by the full-field qualifying contract. The audit names them;
no ranks were inferred from lap times. It records 185 excluded rows without usable
qualifying/finish evidence and 27 DNS/disqualification exclusions.

Finish-order MAE is 3.705 versus qualifying order's 3.268; DNF Brier is 0.1811 versus
the training-rate prior's 0.1637. Lower is better. The candidate remains inactive
and ineligible for promotion. Existing models are preserved.

## Benchmark and collection

Two independent changes were compared offline: single pace blending and Q-only grid
weight 3.3. The run used 1,000 simulations for each seed 42/123/777, PRE/FP2/Q stages
and explicit official archive Q classifications. All inspected training/validation
races are carried forward in the inspection ledger.

On ten already inspected Q races, established finish MAE was 3.601, single pace
blend 3.538 and stronger grid 3.401. Both candidates fail promotion for insufficient
fresh coverage. These are diagnostic results, not a proven accuracy improvement.

A new inactive, source-pinned prospective suite compares the simulation, existing
stage blend, stronger grid and single pace blend. Old suites/config backups remain.
US PRE was captured at the actual current trial time using the preserved 11 October
feature cutoff: no backdating or claim of refreshed PRE inputs. FP2/Q capture when
eligible forecasts exist before race start. Scoring waits for matching official
results. Review requires six fresh races per stage, the declared improvement gate
and no probability-metric regression. No automatic activation or shadow posting.

## Evidence

Artifacts are under outputs/project_next_steps/20261023:

- coverage_repaired/report.json and coverage_after.json: repairs and paired coverage.
- training_coverage_audit.json: fitted cohort and exact Q rank problems.
- retrained_candidate/: preserved inputs, inactive candidate and validation exports.
- benchmark/report.json, summary.csv, predictions.csv: offline comparison.
- prospective_final.log: suite, PRE capture and report locations.
- packaged_api_checks.json and screenshots: executable checks.
- tests_final.log and verification.json: tests and protected-file hash verification.

Repeat a repair/audit with an unused output directory; omit --repair for audit only:

```powershell
.\.venv\Scripts\python.exe -m scripts.repair_training_coverage --workspace "$env:LOCALAPPDATA\RaceWorkbench" --years 2021 2022 2023 2024 2025 2026 --repair --output-dir outputs/coverage-follow-up
```

Q/R repairs do not promise position telemetry for every session. Old archive
versions, candidates, frozen forecasts and delivery receipts remain intact.
