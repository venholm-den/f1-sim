# Promotion lanes, fuller race scores and the season challenger

Three changes to how candidates earn a live change. None of them changes live
settings, the enabled prospective suite or its pinned source files, frozen
forecasts or Discord delivery.

## 1. Two lanes

`src/promotion_evidence.py` puts every candidate choice in one of two lanes.

| Lane | Meaning | Gate |
| --- | --- | --- |
| correctness | Gives the model a fact it was missing | At least six paired replay races, and no metric worse than twice the seed noise (floor 0.0001) |
| accuracy | Changes model judgement: fitted or assumed values, new mechanisms | Unchanged: six fresh races per stage, at least 5% lower paired loss, no Brier regression, Q beats qualifying order |

Correctness candidates today: `grid_penalty_model: announced_v1` and
`sprint_model: sprint_v1`. Every other choice is accuracy, including
`retirement_progress_v1`, because it samples fitted retirement laps. Race Setup
labels correctness choices "(fact fix)".

A correctness pass is evidence for review. It still needs an explicit decision
before any live change.

## 2. Scoring more of each race

`src/race_scores.py` adds four scores to finish MAE and the three Briers:

- **RPS**: ranked probability score over each driver's whole position distribution
- **log score**: minus log of the chance given to each driver's actual position, floored at 0.001
- **pair Brier**: every head-to-head pair (231 for 22 drivers), with **teammate Brier** reported on its own
- **threshold RPS**: win, podium and top-10 only, which every saved forecast and prospective trial already stores

Whole races stay the unit. Seeds are averaged within a race before pairing.

`power_table` reports, per metric, the spread of per-race paired differences,
the gain detectable with 6, 12 and 24 races (one-sided, alpha 0.05, power 0.8),
and how many races the observed gain would need.

```powershell
.\.venv\Scripts\python.exe -m scripts.promotion_check score --arms established multi_sc_v1 team_noise_v1 --output outputs\promotion\rows.csv
.\.venv\Scripts\python.exe -m scripts.promotion_check gate --metrics outputs\promotion\rows.csv --candidate multi_sc_v1 --lane accuracy
```

`gate` also reads rows from other offline benchmarks that write
`round, seed, arm` plus metric columns, such as `benchmark_sprint` and
`benchmark_pair_overtaking`.

### Diagnostic on the 2026 packet

This used `singapore-20261005-v4-venues`: 13 inspected races (rounds 4–16),
three earlier races' pace, the actual grid, 2,000 sims, seeds 42/123/777. These
races are inspected, so the result is a diagnostic, not promotion evidence.

| Arm | Finish MAE | Top-10 Brier | RPS | Log score | Pair Brier | Teammate Brier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Established | 3.665 | 0.1851 | 0.1368 | 3.243 | 0.1930 | 0.2546 |
| multi_sc_v1 | 3.673 | 0.1783 | 0.1321 | 3.007 | 0.1866 | 0.2430 |
| team_noise_v1 | 3.667 | 0.1834 | 0.1356 | 3.179 | 0.1913 | 0.2546 |

Races needed to detect the observed `multi_sc_v1` gain:

| Metric | Mean paired change | SD across races | Races needed |
| --- | ---: | ---: | ---: |
| Finish MAE | +0.008 | 0.031 | worse |
| Loss (MAE + top-10 Brier) | +0.001 | 0.034 | worse |
| Top-10 Brier | −0.0067 | 0.0057 | 5 |
| RPS | −0.0046 | 0.0031 | 3 |
| Pair Brier | −0.0065 | 0.0035 | 2 |
| Log score | −0.236 | 0.178 | 4 |

Two readings:

1. Paired comparisons on shared features and seeds are much less noisy than
   separate race scores, so six races can detect real changes.
2. The gate's loss is dominated by finish MAE, which barely moves for
   candidates that improve probabilities. On this packet `multi_sc_v1` improves
   every probability score and would still fail the 5% loss rule. Changing the
   gate's primary metric is a policy decision. This change reports the
   evidence and leaves the gate as it is.

## 3. One frozen challenger per season

`src/challenger.py` freezes one combination of candidate choices for a whole
season. The frozen file is write-once and records:

- the candidate choices and their lanes
- any parameter overrides
- a hypothesis and the primary metric
- the declared sequential-test bounds
- sha256 hashes of `main.py`, everything under `src`, and the track and power-unit data

Freezing is refused after `freeze_before_utc`, which must fall in the
challenger's season and come before its first session.

```powershell
.\.venv\Scripts\python.exe -m scripts.challenger freeze --spec config\challenger.example.json
.\.venv\Scripts\python.exe -m scripts.challenger verify --frozen outputs\challengers\workbench_v2_2027.json
.\.venv\Scripts\python.exe -m scripts.challenger config --frozen outputs\challengers\workbench_v2_2027.json --output outputs\challengers\run_config.json
.\.venv\Scripts\python.exe -m scripts.challenger evaluate --frozen outputs\challengers\workbench_v2_2027.json --metrics season_rows.csv
```

- `verify` exits non-zero when any hashed file changed. A changed challenger
  is a different challenger, so freeze a new one for a later season.
- `config` writes a validated local run config with Discord posting forced off.
- `evaluate` pairs the challenger's arm (its name) with `live` race by race and
  reports the established gate, the power table and the sequential tests.

`config/challenger.example.json` is an example, not a decision. Choose the real
combination in the off-season from candidates that won on inspected history.

### Sequential test

`betting_e_value` is a test-by-betting e-process. Each per-race paired
difference is clipped to a declared bound, and wealth is averaged over a fixed
grid of bets. Under the null hypothesis (the challenger is no better) the
average stays a supermartingale. The challenger counts as better once the
e-value reaches 1/alpha, which is 20 at alpha 0.05. It can be checked after
every race without inflating false positives.

The bounds are assumptions set before any challenger result: loss 1.0, RPS
0.05, pair Brier 0.05, log score 1.0. A loose bound only makes the test
slower to reach a decision. It does not make it invalid.

### Not yet automated

Hourly automation does not run the challenger yet. Wiring it in touches source
files pinned by the enabled 2026 prospective suite, and changing those would
invalidate its remaining captures. Do it after Abu Dhabi, register a new suite,
and then freeze the 2027 challenger.

`parameter_overrides` are recorded in the frozen file, but the forecast
pipeline does not read them yet. That wiring belongs to the same post-season
change.
