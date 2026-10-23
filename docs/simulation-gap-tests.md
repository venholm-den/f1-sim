# SC/VSC, estimated tyres and independent classification checks

Scheduled source runs keep the live forecast and add these shadow comparisons:

| Candidate | Matched baseline | Change |
| --- | --- | --- |
| `agent_neutralisation_v1` | `agent_laps_v1` | Empirical SC/VSC, compression, restarts and pit discount |
| `pit_inventory_v1` | `pit_scenarios_v1` | Feasible plans and starting ages from frozen tyre estimates |

Both use 1,000 simulations per seed and seeds 42, 123 and 777 alongside the
existing candidates/control. Resolved inputs/evidence are saved. Comparisons
stay within one suite and stage. Six fresh races, 5% improvement and no Brier
regression are still required for review; incremental improvement alone does
not justify replacing the live model. Nothing is promoted automatically.

## Neutralisation

The immutable history packet now retains TrackStatus, race-control messages
and session status. Initial labels use TrackStatus 4 for SC and 6/7 for VSC.
Consecutive VSC/ending labels merge. Known green races remain zero-event
observations. Missing coverage, rain/unknown rain, red flags and unsupported
labels exclude a race rather than fabricating green running. Whole schedules
preserve clustering. Circuit schedules shrink toward pooled dry history with
a fixed five-race prior; there is no parameter search.

The archive has 40 earlier races: 28 usable dry races, five with no events,
16 SC windows and 24 VSC windows. Twelve races were excluded. These are
calibration counts, not accuracy results.

SC slows the physical leader while followers catch a queue at capped pace.
Passing/blue-flag overtakes are suspended; there is no automatic unlapping.
VSC applies common reduced speed and retains gaps. SC ending triggers a
bounded, decaying follower slowdown; VSC ending does not. Sampled boundaries
have at most one integration-step timing error (one second in this protocol);
explicit test windows split steps exactly.

Exposed assumptions: SC multiplier 1.6, catch-up 1.15, VSC 1.4, queue target
one second, restart response 15 seconds and up to 10% follower slowdown.
Net pit loss retains an assumed 2.5-second stationary component and discounts
the rest to 60% under SC or 80% under VSC, charged once. These are not fitted
physics. Elapsed-race fractions scale to a green-race reference. Incident/DNF
coupling, red-flag recovery, wet transitions, sector speeds and era-specific
aid reactivation remain outside this experiment.

## Estimated tyres

New forecasts copy/hash the estimated inventory and stint ledger into frozen
snapshots. Old snapshots stay unchanged; missing frozen inventory skips this arm.
MH/MMH scenarios consume distinct estimated fresh sets. At most one used
representative per compound is allowed, at the largest observed **end** age.
Repeated stints cannot invent extra used sets. Continued used-set availability
is an assumption: barcodes and verified returns are unavailable. Plans record
set IDs, starting ages, source and per-compound confidence, including low
confidence. Infeasible plans are removed and weights renormalised. No feasible
plan for a driver skips the arm. Target race observations, duplicate counts
and invalid ages are rejected.

The same age validator feeds aggregate costs and agent tables. Pit resets
select the declared next age instead of making every set new. Pit timing and
strategy probabilities are not optimised; feasible scenarios retain prior weights.

## OpenF1 checks

The client exposes [`session_result` and `starting_grid`](https://openf1.org/docs/).
Hourly source automation checks after main delivery/trial work. Post-race
checks follow official scoring. `config/classification_checks.json` controls
local requests; absence/disabled means no requests.

Matching requires an explicit circuit, year and scheduled UTC start within
60 seconds. Qualifying must belong to that exact meeting. No `latest` or
country-only fallback is accepted. Pre-race checks compare complete frozen Q
ranks and verified FIA grids, never the target race's result. Post-race checks
require a matching completed FastF1 official score and the existing eight-hour
delay, then compare position and known DNF/DNS/DSQ labels. Unknown flags are
not false. New Q snapshots also cross-check OpenF1 starting tyre age against
the frozen ledger, accounting for unobserved early laps and recording the
age convention. This does not change inventory or certify availability.

New `outputs/classification_checks` folders retain responses, session IDs,
hashes, request/receipt timestamps, source cutoff and disagreements. Retrieval
time is never publication time. Complete checks cache six hours; unavailable,
failed or partial checks retry after one hour without overwriting. API failures
cannot block forecasts or trigger reposts. FIA/FastF1 remain authoritative;
disagreements never automatically change probabilities or scoring labels.

Manual API comparison (new local report, no posting):

```powershell
.\.venv\Scripts\python.exe -m scripts.classification_checks --forecast-folder outputs/app_runs/<forecast>
# After official scoring:
.\.venv\Scripts\python.exe -m scripts.classification_checks --forecast-folder outputs/app_runs/<forecast> --official-folder outputs/app_runs/<score-job>
```

The saved Singapore forecast lacks complete frozen Q ranks; OpenF1's grid
request returned 404. These checks record unavailable, not match. Mutable tyre
files were used only for a functional smoke test, never inserted into its old
frozen inputs. Strict reproduction guards prevent manufacturing prospective
trials from an incompatible older forecast. New eligible forecasts supply
the versioned inputs.
