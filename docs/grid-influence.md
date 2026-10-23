# Grid influence experiment, 23 October 2026

This experiment changes only the difficulty input to the existing simulation.
Live profiles and simulation parameters remain unchanged. The selected candidate
is registered for prospective shadow comparison in the existing hourly PC task.
No extra scheduler or Discord delivery is created. Existing desktop executables
have not been rebuilt; the scheduled source workflow uses the new code.

## Replay protocol

Run with the existing environment, entirely from downloaded detailed archives:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_grid_influence `
  --workspace C:\Users\kyle_\AppData\Local\RaceWorkbench `
  --output-dir outputs\grid_influence\<new-run> `
  --fit-through 2024 --n-sims 1000 --seeds 42 123 777
```

All mapping choices and the split are declared before evaluation. Development is
2021–2024; later scoring is 2025–2026. Each stage is selected independently using
mean finish MAE plus top-10 Brier, averaging seeds within races first. The choice
is saved before later scores are calculated. Later races have already been
inspected and are diagnostic, not fresh validation.

The four mappings are the active circuit coefficient, uniform 0.55, active
coefficient multiplied by 1.25 (capped at 0.95), and an inverse clean-order-change
proxy. The proxy uses strictly earlier same-layout races, shrinking toward the
earlier pooled rate, and falls back to the active coefficient below two local
races. Its declared range is 0.25–0.90. It is a statistical hypothesis, not a
measured overtaking cost. The grid multiplier and all other model inputs are
held fixed; other shadow experiments remain independent arms.

All candidate/control episodes use identical inputs, seeds and driver coverage.
Q classifications require complete unique ranks. Missing roster features, roster
changes and missing sessions skip the entire episode for every mapping; they
are recorded in the report. Twenty-four missing FP2 episodes include weekends
without a downloaded FP2; the report does not claim these all represent data
loss. PRE retains the existing previous-race roster assumption. Archives may
contain later corrections and do not attest original publication timestamps.

## Result

Development selected `active_times_125` for PRE, FP2 and Q independently, with
59, 63 and 77 complete development races respectively.

| Later diagnostic stage | Matched races | Active finish MAE | Candidate finish MAE | Combined loss improvement |
| --- | ---: | ---: | ---: | ---: |
| PRE | 30 | 4.2675 | 4.2550 | 0.28% |
| FP2 | 26 | 4.2223 | 4.2119 | 0.24% |
| Q | 35 | 3.7648 | 3.6905 | 1.95% |

These improvements fall below the 5% review gate. FP2 win and podium Brier scores
worsen. Q's qualifying-order baseline has finish MAE **3.3042**, better than the
candidate's 3.6905. This small grid adjustment does not establish that the full
simulation adds value over qualifying order. No live activation is justified.

## Coverage audit

The five previously unresolved archived races now resolve through explicit
physical venue mappings: Portugal 2021 (Portimão), France 2021/2022 (Paul Ricard),
Russia 2021 (Sochi) and Turkey 2021 (Istanbul). Event-only historical mappings are
restricted to their valid venue periods, so an older French or Portuguese GP is
not assigned a later circuit. Yas Island is recognised as Yas Marina. Melbourne
has an explicit pre-/post-2022 layout split. Conflicting feed hints still fail
closed. Saved archive manifests and frozen venue identities are unchanged.

Circuit evidence increases from 125 races/26 circuits to **130 races/30 circuits**;
Belgium 2021 remains excluded as an aborted classification.

The full Q audit contains 131 saved qualifying sessions: **122 complete unique
classifications and nine invalid**. One complete Q belongs to the excluded
Belgian race, leaving 121 otherwise classification-eligible Q/R pairs before
replay roster/feature checks. The nine invalid groups are:

- 2021 Monaco: MSC missing.
- 2023 Britain: BOT/PER share rank 15.
- 2024 Monaco: HUL/ALO share 14; SAR/MAG share 15.
- 2024 Netherlands: SAI/ALB share 10.
- 2024 Azerbaijan: RIC/GAS share 15.
- 2025 Emilia Romagna: LAW/BEA share 16.
- 2025 São Paulo: BOR missing.
- 2026 Australia: STR/VER/SAI missing.
- 2026 Spain: STR/BEA missing.

Their saved `ClassifiedPosition` and `Status` fields do not supply replacement
ranks. They remain excluded from Q benchmarks, without fabricated ranks or
mutation of provider data. Correcting them requires independently checked
complete classification evidence. Details and input hashes are exported in
`qualifying_coverage.csv` and the benchmark JSON.

## Prospective collection

`scripts.prediction_trials --register --grid-candidate <candidate.json>` copies
the inactive candidate into a new immutable suite. Supply `--inspected-reports`
with the earlier suite and benchmark report so inspected outcomes cannot become
fresh evidence. The CLI backs up the prior local configuration before switching
the pointer. Existing captures and scores are never rewritten.

The registered `grid_influence` arm uses the same seeds (42, 123, 777) and 5,000
simulations per seed as `simulation`. Its exact coefficient, mapping evidence,
inputs and candidate hash are frozen with each capture. It is scored separately
for PRE, FP2 and Q on matched races. Registration pins participating source
hashes, including the circuit registry and track loader. At least six fresh
races per stage, at least 5% lower combined loss, no probability regressions,
and Q beating qualifying order are required for review. Automatic activation
is disabled regardless of scores.

The US PRE shadow was captured after registration on 23 October, using the
unchanged saved 11 October PRE feature cutoff. Its timestamp is not backdated
and it contains no FP1 observations. It is a newly generated shadow comparison
of old PRE inputs, not a newly issued forecast at the original PRE time. Future
eligible captures come through the existing hourly source task. Race outcomes
and future FP2/Q captures were unavailable at verification time.

The reviewed candidate preserves the benchmark's selected mappings. A later
source revision restricts event-only venue aliases outside the 2021–2026 sample;
all 130 observation identities were verified unchanged. The original candidate,
source provenance and intermediate suite remain preserved separately.
