# Experimental car agents

The original `agent_laps_v1` scope below is preserved as the comparison
baseline. The separate [SC/VSC shadow arm](simulation-gap-tests.md) now adds
sampled neutralisation, compression, restarts and pit discounts. Estimated
tyres are tested independently in the pit model before combining changes.

`agent_laps_v1` is an opt-in, local-only candidate. It adds interactions to the
existing pace/retirement features. It is not a calibrated vehicle dynamics or
2026 energy management model, and is not eligible for live promotion yet.

## Changes to the proposed equations

| Proposal | Candidate implementation and reason |
|---|---|
| Sort cumulative lap times to find track neighbours | Shared clock, unwrapped progress in laps and circular physical neighbours. Classification separately uses completed laps and interpolated control-line crossings. This handles a faster car catching a backmarker. |
| Swap positions after an overtake roll | A successful roll permits the following car to close the remaining physical gap. The pass is counted only when its progress crosses the car ahead. Failed moves constrain progress; simultaneous updates propagate blocking through trains. |
| Fuel always starts at 110 kg | Configurable initial mass; 70 kg is an explicit sensitivity assumption, not a regulatory maximum or measured load. Fuel is nonnegative and burns at completed laps. |
| Subtract fuel burn from an unspecified base pace | Use `alpha * (midlap_fuel - reference_fuel)`. Existing race pace is treated as mean-fuel pace, with reference at half the initial load. This centres the fuel contribution instead of adding a second whole-race fuel penalty. A zero-fuel input requires reference fraction zero. |
| Multiply thermal wear by 1.15 each following lap | Heat relaxes toward 1 in traffic and toward 0 in clean air, bounded to [0,1]. Irreversible wear adds slowly and is capped. Both reset on a tyre change. At 30 laps, the proposed multiplier would be approximately 66, so it cannot be used unchanged. |
| Fit quadratic degradation directly to lap times | Compound offsets and linear slopes reuse the declared pit-scenario assumptions. A nonnegative quadratic term is configurable, default zero. None is described as fitted: fuel burn, track evolution, traffic and stint selection confound raw lap times. |
| Universal DRS gain | Default aid is disabled. `legacy_drs_proxy` requires 2011–2025; `electrical_proxy` requires 2026 or later. A supplied lap gain is only an effective sensitivity proxy, not ERS/battery simulation. Active aero available to both cars is absorbed into base pace. |
| Overtakes / season mean as a probability modifier | Explicit passability in [0,1], with a negative logistic intercept. Without an override, the existing track difficulty supplies the labelled proxy `1 - difficulty`. Historical total overtakes are confounded by opportunities, weather, field size and grid order. |
| Independent overtake roll every update | Convert an assumed per-lap probability into time exposure: `1 - (1 - p_lap) ** (dt / clean_lap_time)`. Following duration and actual catch/contact are also required. A granted attempt persists until completion or loss of proximity. |
| Blue flags only for the race leader | Any car catching a car about a full lap behind can receive a yielding pass. Each completed encounter incurs its assumed costs once. Blue-flag passes are counted separately from racing passes. |
| Derive pure pit-lane loss from one pit lap | Reuse explicit **total net pit loss**, charged once, separate from tyre costs. Pit cars leave the traffic set and rejoin after the delay. No claim of measured lane-only or stationary time. |

FIA's [2026 overview](https://www.fia.com/news/f1s-new-era-everything-you-need-know-about-how-fia-making-formula-1-more-competitive-more)
distinguishes active aero from the electrical overtaking aid. The current
[Sporting Regulations, Issue 09](https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_b_sporting_-_iss_09_-_2026-10-01.pdf)
set out detection/activation-line eligibility in B7.2, finish procedure in B5.16,
and completed-lap/crossing-order classification in B2.5.5. The candidate's
continuous proximity proxy does **not** implement exact detection lines.
FastF1's [lap schema](https://github.com/theOehrly/Fast-F1/blob/master/fastf1/core.py)
provides pit entry/exit timestamps. Their difference includes travel and service,
and a pit visit can straddle lap records; it is not automatically a stationary
tyre-swap duration or net race-time loss. Fit total losses from matched green-flag
in/out laps or a validated timing source, with fuel, warm-up and traffic controls.

## Running and inspecting it

Use a run config with `model.race_engine = "agent_laps_v1"` and optional
`model.agent_settings`. `config/agent_layer.example.json` is a local example.
Existing pit-plan JSON can supply each scenario's compounds, stops and total
net `pit_loss_seconds`; optional `tyre_ages` specifies the historic age at the
start of **each** stint. The default remains equal-weight M-H / M-M-H plans.

```powershell
.\.venv\Scripts\python.exe main.py --config config/agent_layer.example.json --no-discord
```

This follows the normal data-loading pipeline; it is not an offline replay.
For controlled offline comparisons use `scripts.benchmark_feature_ablations`
with `--variants legacy agent_laps_v1`, explicit prior/inspection reports,
saved Q classifications, and the existing chronological promotion gates.
Other candidates, including qualifying posterior pace and survival DNF, can be
combined manually, but independent ablations should precede judging a combination.

The main pipeline saves the fully resolved settings in `simulation_inputs.json`.
Raw results expose fuel, tyre age, heat/wear, completed laps, pit stops, traffic
loss, racing passes and blue-flag passes. `projected_race_time_seconds` here means
elapsed time at the **last completed crossing**, including for retirements and
lapped finishers; do not compare it as a full-distance pace forecast. DOTD is
unavailable (false) and fastest lap uses simulated lap crossings among surviving
cars. Retirees are excluded from that secondary statistic in this increment.
No fastest-lap bonus points are added.

The common clock uses 2-second steps, bounded to at most 5 seconds. Timing-line
crossings and net pit delays are interpolated; changing fuel/tyre/traffic within
a step remains an approximation. Compare 2/1/0.5-second runs and seed ensembles
before trusting close battles. Individual traces are available from the
`run_agents(..., record_trace=True)` kernel for a one-race experiment.

The supplied manual config chooses **1 second** as a more conservative starting
point. In a 23-car saved-input stress check at 1,000 simulations, maximum driver
mean-position differences versus 0.5 seconds were 0.436 places at 2 seconds and
0.117 at 1 second. Runs took about 12/22/64 seconds respectively on this machine
while other checks ran. Per-step RNG trajectories differ across resolutions:
these differences combine Monte Carlo variation and numerical effects. This
single stress check does not establish distributional convergence. Historical
replay of the predeclared default candidate still uses 2-second steps; do not
silently attribute its scores to the example's 1-second configuration.

## Boundaries and acceptance

This first candidate supports dry races. It rejects an explicitly wet input.
Prescribed `neutralised_windows` can disable passing/aid and apply a shared slow
pace for correctness tests. They are **not** a full SC/VSC model: no generated
events, field bunching, unlap procedure, pit discounts, restart or red-flag tyre
changes are simulated. Grid position uses an assumed initial time spacing;
there is no stochastic launch/battle model. Pit loss is a control-line delay,
not pit-road geometry, stationary-service sampling or team stacking. There is
no inventory model, strategy agent, thermal telemetry fit, energy state,
push/conserve choice or correlated incident generation. Finish-distance DNF
sampling remains independent of pace and stops at a completed lap, rather than
a sector-level failure point. These limits affect accuracy and need separate
ablation/calibration work.

The inherited absolute lap reference has not been jointly fitted to fuel, tyre
age and track evolution. Treating it as mean-fuel pace centres the assumed fuel
effect, but does not prove a physical reference convention for the original
features. Adding explicit tyre-age curves also requires a consistent baseline
fit. Finish-ranking scores alone cannot validate absolute lap times or tyre
physics; those need separate clean-stint residual checks.

Tests cover physical neighbours across lap counts, blocking/passing coherence,
blue flags, chequered-flag lapped finishers, retirement state, bounded thermal
and fuel states, neutralisation, seed repeatability, step convergence, roster
order, configuration gates and default compatibility. More realistic mechanics
are useful only if predictions improve on chronological races and beat the Q
order baseline. Previously inspected outcomes remain diagnostic; the existing
six-development/six-fresh-race, 5% loss improvement and no Brier regression gates
remain in force. No new automatic trial arm or live activation is introduced.
