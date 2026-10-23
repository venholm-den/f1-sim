# Race weather and delayed starts

## What changed

New beta/automated forecasts capture a separate race-target weather briefing at
the circuit coordinates. The request uses UTC, covers two hours before the
scheduled start through the assumed race duration plus a two-hour delay, and
archives the responses and capture timestamps. `race_weather.json` and
`race_weather_raw.json` are copied into **new** frozen forecasts and protected by
the manifest hashes. Existing snapshots and Discord delivery plans are unchanged.

The informational Discord field shows ensemble rain guidance for the scheduled
start and starts delayed by 30, 60 and 120 minutes, alongside the weather capture
time. New session forecasts include a frozen capture. Between sessions the existing
scheduler also saves append-only local updates every six hours, increasing to
hourly in the final 48 hours before the race. Updates live separately under
`outputs/race_weather_updates/<year>_<round>/`; they never rewrite the original
forecast or repost its Discord message. The standalone command below can refresh
weather and simulate its sensitivity into a new local experiment directory. It
never posts to Discord.

The older session-weather fallback now requests GMT hours and converts the target
to UTC, and refuses targets outside the returned time range. Previously it stripped
the target timezone, requested local hours and selected the nearest hour even
when the session lay outside forecast coverage. Observed session weather remains
the established live model input.

## Why this approach

The current `summarize_weather` prefers weather observed during the input session;
even its fallback targets that session rather than the race. `simulate_races`
accepts global weather modifiers but has no delayed-start clock or timed weather
trajectory. Acquiring race weather addresses a real input gap; it does not prove
that the existing hand-set wet-weather modifiers are accurate.

Adopt the existing Open-Meteo provider rather than adding another dependency or
paid subscription. Adapt its ensemble member trajectories to the race window;
build the narrow UTC/window/archive layer locally. This bounded source and API
review used the root agent only; it is not an exhaustive vendor benchmark.

- [Forecast API documentation](https://open-meteo.com/en/docs) specifies
  preceding-hour precipitation accumulation. Wind is requested in m/s. Best-match
  output provides temperature, humidity, rain, gusts, visibility and weather codes.
- [Ensemble API documentation](https://open-meteo.com/en/docs/ensemble-api)
  provides individual ECMWF IFS 0.25-degree trajectories. The `ecmwf_ifs025`
  identifier was checked against the official page and a successful API response;
  the Singapore check returned 51 members. Regional grid cells are coarser than
  the circuit, and hourly values can be interpolated from coarser model steps.
- Coherent member paths preserve temporal dependence. Do not derive the chance
  of rain somewhere during the race by adding hourly probabilities or assuming
  independent hourly rain events.
- [Single Runs API documentation](https://open-meteo.com/en/docs/single-runs-api)
  describes original model runs. Historical validation must use forecasts that
  were actually available before the prediction cutoff; initialisation time alone
  is insufficient. A stitched historical forecast or actual race weather is not
  a substitute for that pre-race information.

The public API is used for this personal project without credentials. Review
[Open-Meteo's usage terms](https://open-meteo.com/en/terms) before commercial use;
this change establishes neither a paid service nor production availability.
Provider failures, missing coordinates, missing members and horizon gaps retain
unknown values. They do not become evidence of dry weather. The raw payload
retains provider-selected grid coordinates as well as the circuit coordinates.

## Conditional delayed-start experiment

```powershell
cd C:\code_project\f1-sim
.\.venv\Scripts\python.exe -m scripts.race_weather_shadow `
  --forecast-folder outputs/app_runs/20261004T070237Z_d9f7e385 `
  --sims-per-member 200
```

This writes a new local `outputs/race_weather_shadow/<timestamp>/` with raw
responses, the weather briefing, source hashes, scenario predictions and an HTML
preview. Features come from the verified frozen run. Weather uses the **new capture
time**, which can be later than that feature cutoff; these predictions are labelled
`weather_shadow_unvalidated`, never as the original prospective forecast.

Each complete member gets the same number of simulations. The existing weather
heuristics use its mean temperature/humidity/wind and whether an overlapping
hour has more than 0.1 mm precipitation. Driver averages and probabilities are
averaged over members; quantiles are deliberately not averaged. Seeds are shared
across conditional start windows to reduce comparison noise. The experiment
does not train a weather model, alter the saved feature table or replace the live
forecast. The current simulation source is fingerprinted separately from the
historical frozen run.

Default duration is a two-hour weather window (`--duration-minutes` can change
this). Partial-hour rain totals are prorated under a uniform hourly intensity
assumption; the wet-hour flag counts any qualifying hourly interval overlapping
the window and does not locate a shower within that hour. Antecedent two-hour
rain totals and a 4 mm/hour heavy-rain frequency are captured as diagnostics.
That threshold is **not** a rule for delaying an F1 race.

`delay_probability` remains unknown. Weather-based start decisions require
event-level evidence: scheduled versus actual start, reason for delay, rain
intensity, standing water, visibility, lightning, circuit drainage and operational
constraints. Neither rain probability nor ensemble heavy-rain frequency estimates
that decision directly. Delays can also have non-weather causes.

`--delay-weights` accepts four explicit assumptions summing to one, in
scheduled/+30/+60/+120 order. Only supplying those assumptions produces an
additional weighted prediction. It is labelled `explicit_user_assumption`, not
calibrated delay probability. Uniform weather-member weights within delayed
windows do not capture race control preferentially choosing a safer restart;
this dependence needs a joint weather/start model before live use.

The experiment retains full race distance. Shortened races, aborted races,
interruptions, changing tyre choices and driver-specific wet skill are not
modelled. Track temperature is unknown rather than derived from air temperature.
Rain before the start is captured but not converted to standing water or wet-track
state without a drainage/drying model. Singapore 15-minute interpolation is not
treated as radar nowcasting.

## Acceptance and promotion

Immediate acceptance: correct race/UTC target, complete temporal coverage,
preceding-hour rain semantics, coherent member frequencies, unknown failure
states, changed weather windows after delay, unchanged live predictions and
historical frozen bytes. Tests cover these contracts; the live Singapore run is
an acquisition/sensitivity smoke check, not an accuracy benchmark.

Stop before live promotion if original pre-cutoff weather forecasts or reliable
delay labels are unavailable. Use whole-race chronological development/holdout
partitions, keep lead times comparable, and score wet/dry and delayed-start
calibration separately. Fit a small, regularised event-level delay model only once
there are sufficient confirmed delay and non-delay events. Report label coverage,
Brier/calibration and sample sizes; repeated simulation seeds are not new races.

Driver forecast promotion remains subject to `docs/accuracy-improvements.md`:
at least six development and six fresh validation races per requested stage,
at least 5% lower combined finish MAE + top-10 Brier and no win/podium/top-10
Brier regression. A pass is evidence for review, not automatic promotion.
