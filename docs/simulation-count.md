# Simulation count comparison, 25 October 2026

New Race Setup, Simulation Centre and official forecast runs default to 100,000
simulations. The existing Windows forecast task explicitly passes that count.
Seed 42 and the existing model settings remain the defaults. Existing frozen
forecasts are preserved; their original 10,000-simulation protocol is still
recognised when classifying saved forecasts. Packaged executables need a separate
rebuild to include these source changes.

The internal simulation function and CLI fallback retain their compatibility
defaults: normal application and CLI runs supply the count from the updated
configuration. This avoids editing source files pinned by prospective trials.
The registered candidate suite and its configuration are not re-pinned.

## Historical comparison

`scripts.benchmark_simulation_count` compares 10,000, 50,000 and 100,000 simulations
with seeds 42, 123 and 777 on the established model. It loads checksum-verified
local archives without downloading sessions. Each count uses the same features,
circuit difficulty and stage weather. Historical feature construction uses only
earlier races, with five baseline races to match the default application setting.
2024 supplies initial history; 2025 and 2026 supply scored race outcomes.

PRE, FP2 and Q are reported separately. Incomplete forecast/result driver coverage
and invalid qualifying classifications are excluded, without imputing Q ranks.
Seed results are averaged within race; races then receive equal weight. Paired
95% bootstrap intervals resample whole races, not seeds or simulated outcomes.
The comparison reports finish MAE, win/podium/top-10/DNF Brier scores, computation
time and the average probability standard deviation across seeds.

These races have already been inspected in earlier research. Results are
historical diagnostics, not fresh validation. More simulations reduce Monte
Carlo noise; they cannot repair biased features or model assumptions. Identical
seeds do not produce nested draws when simulation array sizes differ.

Reproduce from the main checkout using its existing environment:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_simulation_count `
  --workspace C:\Users\kyle_\AppData\Local\RaceWorkbench `
  --output-dir outputs/simulation_count/<new-folder>
```

Outputs are under `outputs/simulation_count/20261025-100k`: source/input hashes,
seed metrics, race metrics, per-driver predictions, grid baseline, stage summary,
paired comparisons, coverage exclusions and the final report. Existing output
folders cannot be overwritten. The previous Windows task definition and a
saved-forecast classification check are retained beside the comparison.

## Results

The run completed 96 matched stage episodes across 39 distinct races, with
three seeds at each count (864 simulation calls). There were 27 excluded stage
episodes. Lower finish MAE is better:

| Stage | Races | 10,000 | 50,000 | 100,000 |
| --- | ---: | ---: | ---: | ---: |
| PRE | 33 | 4.0065 | 4.0064 | 4.0070 |
| FP2 | 27 | 4.0520 | 4.0519 | 4.0514 |
| Q | 36 | 3.6519 | 3.6536 | 3.6524 |

Relative to 10,000, the paired 100,000-minus-10,000 finish MAE changes and
race-bootstrap 95% intervals were PRE +0.000545 [-0.001685, +0.002886],
FP2 -0.000583 [-0.002588, +0.001411] and Q +0.000434
[-0.001062, +0.001939] positions. These do not establish a meaningful
finishing-position accuracy improvement. Probability accuracy was mixed:
Q win Brier improved from 0.034609 to 0.034484, while Q DNF Brier worsened
from 0.134919 to 0.134983. Full metric comparisons are in the output CSV.

Average top-10 probability standard deviation across seeds fell by about 68%
at every stage versus 10,000. Typical simulation computation rose from
0.104–0.105 seconds to 0.785–0.791 seconds (about 7.5 times), or about twice
the 50,000 runtime. These timings exclude feature building, data collection,
chart generation and output publication. The practical benefit is steadier
Monte Carlo probabilities; this comparison does not support the claim that
100,000 simulations produces substantially better historical predictions.

The full source regression suite passed 873 tests. All 21 existing frozen
forecasts retained their prior official/personal classification. The Windows
task was re-read after updating its explicit argument to 100,000; it was not
manually launched. Frozen forecast bytes and delivery receipts were untouched.
