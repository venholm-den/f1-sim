# Forecast publication contract (v1)

Release-plan items for 3 November (publication contract) and 7 November (publishing and stale-data rehearsal), started early. No hosted service, credentials or network calls exist yet. Nothing here uploads, changes model settings or touches frozen forecasts.

## What gets published

`src/app_services/publication.py:build_publication` turns one verified frozen snapshot (`frozen/manifest.json` from `beta.freeze_snapshot`) into a payload. It refuses an edited snapshot and anything that is not a prospective pre-race forecast.

| Field | Meaning |
| --- | --- |
| `contract`, `schema_version` | `f1-sim.forecast-publication`, `1` |
| `publication_id` | `<year>-r<round>-<stage>-<first 12 hex of the frozen manifest sha256>`. Retrying one snapshot always gives the same id. |
| `kind`, `visibility` | Always `official`; `subscribers` or `preview`. Personal scenarios are a different kind and are rejected. |
| `event` | Year, round, name, scheduled race start (UTC) |
| `stage`, `available_sessions` | Input stage (PRE, FP1, FP2, FP3, SQ, S, Q) and the completed sessions it used |
| `input_cutoff_utc`, `generated_at_utc` | Feature cutoff and snapshot freeze time (producer clock, unattested) |
| `model` | Caller-supplied `model_id`, app version, fingerprint of the model source hashes, and n_sims/seed/overtaking difficulty |
| `provenance` | Frozen manifest sha256, frozen input file hashes, timestamp authority, session evidence |
| `limitations` | Copied from the manifest |
| `predictions` | One row per driver: `avg_finish`, win/podium/points/DNF chance |
| `checksum` | sha256 of the canonical JSON (sorted keys, no whitespace) without the `checksum` block |

Publication time is not part of the payload. The store records it when it accepts the payload, so a retry is byte-identical to the first attempt.

`validate_publication` is the authoritative check. The [JSON Schema](schemas/forecast-publication-v1.schema.json) describes the structure for other clients. The validator also rejects:

- a checksum or `publication_id` that does not match the content
- a stage that is not backed by its sessions (PRE only with none completed)
- a forecast generated before its cutoff, or at/after the race start
- fewer than 15 drivers, duplicate drivers, probabilities outside 0–1, average finish outside the field, or win chances that do not sum to one (±0.02)
- producer-only keys (paths, credentials, tokens, webhooks, API keys) at any depth, and strings that look like local paths

Accepted and rejected examples are in [schemas/examples/forecast-publication-v1](schemas/examples/forecast-publication-v1). Regenerate them with `python -m scripts.publication_rehearsal --write-examples docs\schemas\examples\forecast-publication-v1`; the tests check each one still gets its expected verdict.

## Store behaviour

`LocalPublicationStore` is a file-backed stand-in for hosted storage with one producer:

- Snapshots are write-once under `snapshots/<year>-r<round>/<publication_id>.json`. The same id with the same checksum is a `duplicate`, and a different checksum is rejected as a conflict.
- The per-event `latest` pointer is replaced atomically (temp file and `os.replace`). It only moves forward: more completed sessions first, then the newer run. A late retry of an older forecast, or a fresh run on fewer inputs, is stored but does not become latest.
- A duplicate publish still re-applies the pointer, so a retry repairs a crash between the snapshot write and the pointer update.
- Failed validation is logged to `rejections.jsonl` and recorded as a failed update. The previous forecast stays.
- Successful publishes also count as a producer heartbeat.

`read_latest(event, now)` is what a client shows:

| State | When |
| --- | --- |
| `current` | Valid latest forecast, producer seen within 2h, newer than 30h, no failed update since the last success |
| `stale` | Still served, with reasons: producer offline, forecast age, or "the latest Q update failed; showing the previous forecast" |
| `closed` | Race has started; the final pre-race forecast |
| `unavailable` | Nothing published yet, or the stored snapshot fails its integrity check (never served) |

The 2h and 30h thresholds are placeholders, set as constructor arguments, until the hosted design is agreed on 31 October.

## Rehearsal

```powershell
.\.venv\Scripts\python.exe -m scripts.publication_rehearsal --output outputs\publication_rehearsal
```

This runs nine fixture steps in a temporary folder: FP2 published, duplicate retry, conflicting retry, Q fails validation, an interrupted pointer update repaired by retry, a late older FP2, a failed producer run, the producer offline overnight, and the race start. It prints PASS/FAIL per step with what the client would see, and exits non-zero on any failure. `tests/test_publication.py` runs the same rehearsal.

## Not covered yet

- Hosted storage, authentication, entitlements and outbound publisher credentials (10–14 November and later).
- Concurrent producers. The store assumes one producer, matching the single-PC plan.
- A trusted publication timestamp. The store's clock is used; the producer's clock remains `local_clock_unattested`.
- What `model_id` names. It is whatever the producer passes (the rehearsal uses `established`) until the 12 December model selection.
