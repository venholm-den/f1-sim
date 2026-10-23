# Qualifying pace and cohort follow-up, 23 October 2026

## Stable collection

The enabled suite remains
`outputs/prediction_trials/suites/20261023T195024249769Z_57817a83/suite.json`,
SHA-256 `f0e9901f678c30aa447347c76dca85e2d8031277b40c5ef36645bc8a15fdec6e`.
Its four candidate arms are `stage_blend`, `stronger_grid`, `single_pace` and
`grid_influence`, alongside the established simulation control. No new arm,
source re-pin, live parameter change or Discord delivery was made.

The latest capture/scoring review found one US PRE capture and zero scored
race-stage results. The latest source forecast was FP1, correctly rejected as
an unsupported trial stage. FP2 and Q remain separate future opportunities;
FP1 does not substitute for FP2. The existing hourly Windows task is enabled,
uses the canonical checkout and last returned success. A thread review is
scheduled for Mondays at 10:00 Europe/London; it reports meaningful new evidence
or actionable failures and otherwise stays quiet. Source collection/scoring
continues through the existing task.

## Nine classification investigations

`scripts.audit_qualifying_classifications` downloaded the published F1 Q tables,
retained the HTML and compared driver numbers with checksum-verified saved
classifications. These are independent website checks of the saved table,
although their underlying timing sources may be shared.

| Saved Q episode | Independent finding | Current contract |
| --- | --- | --- |
| Monaco 2021 | F1 table omits MSC; other 19 ranks agree | Keep excluded |
| Britain 2023 | BOT is DQ, rather than a second P15 | Keep excluded |
| Monaco 2024 | HUL and MAG are DQ, rather than duplicate P14/P15 | Keep excluded |
| Netherlands 2024 | ALB is DQ; SAR is absent from the web table | Keep excluded |
| Azerbaijan 2024 | GAS is DQ, rather than a second P15 | Keep excluded |
| Emilia Romagna 2025 | BEA is P19 rather than saved P16; TSU is NC rather than saved P20 | Keep excluded |
| São Paulo 2025 | F1 table omits BOR; other 19 ranks agree | Keep excluded |
| Australia 2026 | F1 table omits STR, VER and SAI; other 19 ranks agree | Keep excluded |
| Spain 2026 | F1 table omits STR and BEA; other 20 ranks agree | Keep excluded |

Four web tables match the complete saved entrant roster; five omit entrants.
None supplies a legitimate numeric 1–N permutation for the full saved roster.
The Imola Bearman discrepancy is a genuine numeric correction, but correcting
it alone cannot make that full field eligible while Tsunoda remains officially
NC. No missing, DQ or NC position was replaced with row order, a Sunday grid
position or a fastest-lap rank. The archive and present feature contract remain
unchanged, so **usable training/benchmark race coverage has not increased**.

Evidence is in `outputs/qualifying_classification_audit/20261023-r2/`:
`report.json`, `comparisons.csv`, nine raw HTML pages and per-race comparisons.
The report records exact source URLs, retrieval times and source/archive hashes.

FIA final classifications for Imola 2025, São Paulo 2025, Australia 2026 and
Spain 2026 were also accessible through web retrieval. The Spanish classification
contains only 20 numbered entrants. Local FIA PDF downloads returned HTTP 403;
`outputs/qualifying_classification_audit/20261023-fia/report.json` records those
failures. They are not claimed as locally preserved or fully parsed evidence.

Extending coverage requires a separately versioned feature contract that preserves
the full roster and represents unclassified/disqualified entrants explicitly.
Training on the valid classified subset may then be possible, but full-field
inference and baseline comparison need a declared missing-rank policy. Simply
assigning the remaining numbers would manufacture evidence. Such a contract
would require a new cohort and cannot modify the present source-pinned suite.

## Pace comparison

`scripts.benchmark_qualifying_pace` compares only `legacy` and
`qualifying_partial_pooling_v1`, at Q, from the detailed desktop archive.
The primary recent-history length is two races; five is a predeclared sensitivity.
Both use seeds 42/123/777 and 1,000 simulations per seed. Qualifying-order and
recent-form baselines use identical complete-driver episodes. Partial episodes
are skipped for both simulation variants. The existing pace posterior fits only
earlier Q/race pairs, with unchanged priors and no grid adjustment.

Development is 2021–2024; later 2025–2026 races are inspected diagnostics.
The input archive hashes, failed classifications, source hashes, attempted-race
ledger, predictions, calibration bins and per-race metrics are retained. There
are no fresh validation races in this retrospective comparison.

Screening for a possible new shadow cohort requires development selection,
at least six matched later diagnostic races, at least 5% lower paired
finish-MAE-plus-top10-Brier loss, no outcome Brier regression and Q finish error
below qualifying order. A historical screening pass would justify review for
separate prospective collection only. Live promotion still requires the declared
fresh evidence gates. Agent, pit and weather experiments remain parked.

The primary two-race-history comparison completed 77 development and 35 later
matched Q episodes. Later finish MAE is **3.6894** for partial-pooling pace,
**3.7648** for the established simulation and **3.3042** for qualifying order.
Combined loss improves **2.17%**, below 5%, and win Brier regresses from
**0.03444** to **0.03537**. The candidate improves development loss but fails
the later diagnostic screening criteria. This is not a promising addition to
the stable cohort. Primary artifacts are in
`outputs/qualifying_pace_followup/20261023-r2/history_2/`.

An input audit found usable Q timing in every one of the 121 eligible sessions:
2,422 of 2,449 driver rows have qualifying timing under the current feature
contract. The missing-timing fallback is not the dominant explanation for the
weak overall result. This establishes feature availability, not that fastest
times across different Q segments are comparable or add independent race-pace
information. See `q_timing_coverage.csv` beside the benchmark directories.

Reproduce in a new output folder:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_qualifying_pace `
  --workspace "$env:LOCALAPPDATA\RaceWorkbench" `
  --output-dir outputs/qualifying_pace_followup/NEW_RUN `
  --inspected-reports outputs/grid_influence/20261023T194144Z/benchmark-r2/report.json
```

## Verification

The full regression run passed **667 tests** with two warnings; six new checks
cover special-position preservation, session identity, the qualifying-order
screen and output overwrite refusal. The active suite and all its pinned inputs
and source files still verify. All 161 files in the earlier protected-file
manifest match their saved hashes. See
`outputs/project_next_steps/20261023/followup_full_tests.log` and
`followup_integrity.json`. Existing binaries were not rebuilt.
