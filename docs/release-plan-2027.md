# Production release plan: 2027 season

Planning baseline: 24 October 2026. Owner: Kyle; implementation and evidence gathering supported by Codex. Target: **6 March 2027**, conditional on the release gates below.

The [official 2027 calendar](https://www.formula1.com/en/racing/2027) currently lists Bahrain testing on **24–27 February** and the first Grand Prix on **12–14 March**. The opener is a Sprint weekend ([Formula 1 announcement](https://corp.formula1.com/2027-calendar-announced-with-10-sprint-events/)). Freeze the release candidate on **20 February**, review testing integration on **27 February**, and make the final go/no-go decision on **4 March**. Recheck official dates in January and before the opener.

## Recommended release scope

Ship a stable, local-first Windows 11 x64 desktop application using the existing Python, pywebview and PyInstaller architecture. The essential journey is setup and data access → forecast → inspect assumptions → review and score → export. Improve core usability and accessibility within the current stack. A full visual redesign needs a separate direction decision.

Defer cloud hosting, central accounts, billing, automatic updates, engine migration and a frontend rewrite. Include fantasy features only if official 2027 rules and prices can be verified; otherwise clearly disable or defer them. Choose the minimum hardware target and distribution audience during the early feasibility gates.

This plan schedules engineering work; it does not authorize purchases, contacting pilot users, changing production services, promoting experimental models or publishing a release. Those decisions belong to Kyle at their named gates. Calendar reservations are personal work sessions, not automated execution.

## Capacity and scope control

Budget: **6 hours per active week**, 17 full weeks (**102 hours**) plus **3 hours** of pre-opener support, **105 hours total**. Keep **21 December–3 January** clear. Nine hours of pre-release contingency are embedded on 15 December, 30 January, 9 February, 18 February and 2 March; the two final support sessions add three hours. This leaves 93 hours of planned delivery and governance work. Task estimates are timeboxes, not proof that every item fits.

At each Saturday gate, record evidence, remaining effort, owner and blockers. Cut optional scope when work exceeds the remaining capacity. Do not absorb overruns by removing acceptance checks. Unresolved provider rights, security, installation or recovery blockers mean HOLD; move the release or retain private beta status. The date is a target, not a waiver.

## Scientific evidence and protected runtime

Keep PRE, FP2 and Q separate and preserve the existing four-model cohort. Independently version the newer form/risk experiment; do not merge cohorts, rewrite frozen forecasts, re-pin old evidence to changed source, or count seeds and stages as additional races. Before release development touches core code, document an isolated stable scientific runtime and an explicit scheduler-routing decision. This planning change does not alter the running task.

The current source baseline reports 841 Python and six JavaScript tests; this is not packaged or clean-machine evidence. Live model defaults remain unchanged. Consult [accuracy improvements](accuracy-improvements.md) and [prospective trials](prospective-prediction-trials.md) for authoritative promotion checks.

New model promotion requires at least six fresh distinct races per requested stage, at least 5% paired loss improvement, no Brier regression, and a qualifying-stage candidate must beat qualifying order, followed by explicit review. Historical factor analysis is diagnostic, not prospective proof. Only six 2026 weekends remain including the current US event, ending [4–6 December in Abu Dhabi](https://www.formula1.com/en/racing/2026); stage availability and capture timing can leave fewer eligible events. Do not promise a new model by March or weaken the threshold to meet the date.

Use the established model if experiments remain inconclusive, with honest descriptions of forecast limitations and experimental outputs. If the agreed product promise requires demonstrated predictive improvement and evidence is insufficient, reduce that promise or delay. Pre-season testing validates feed access and integration; it is not race-outcome validation and must not become a last-minute calibration exercise.

## Mandatory release acceptance

| Area | Evidence required before go/no-go |
| --- | --- |
| Scope and claims | Approved must-have/deferred list, supported OS and hardware, accurate forecast limitations; no unsupported accuracy or calibration claims. |
| Provider access and rights | Real sign-in/download and safe expiry recovery; bounded handling of offline/401/403/429 cases. Review data-source terms, redistribution, branding and intended distribution separately from dependency licences. Unresolved permissions block distribution. |
| Data correctness | Timestamp cutoffs; announced penalties; roster substitutions; explicit DNS/DQ/NC handling; normal and Sprint state matrix. Bahrain rehearsal must work without an FP2 session. |
| Reliability | At least 20 defined failure/recovery scenarios, including interruption, cancellation, retry and deduplication; successful isolated backup, restore and upgrade; frozen outputs and delivery receipts preserved. |
| Usability and pilot | Forecast-to-export task walkthrough, readable missing-data/assumption states, keyboard/contrast/reduced-motion checks; at least three actual pilot users complete onboarding and the core journey. Record native Windows observations. |
| Package | Versioned onedir ZIP, complete internal dependencies, hashes and chosen signing route; actual clean supported Windows installation and core journey without development Python/Node/MATLAB. Verify WebView2/fallback and minimum hardware. Source tests alone cannot pass this gate. |
| Security and provenance | Local API and file-boundary review, no bundled credentials/private data/raw archives, redacted support diagnostics, dependency inventory/notices, traceable source/build/artifact hashes. Signing expenditure requires a separate decision. |
| Operation and support | User setup, privacy, limitations, update, support and rollback instructions; rehearsal of upgrade and rollback; explicit release owner and known-issue list. Zero unresolved P0/P1 defects. |
| Scientific policy | Stage-specific evidence audit; documented model selection and limitations; no automatic experimental promotion. Factual 2027 reference updates are versioned and verified. |

P0 means data loss, secret exposure or unusable application; P1 means a broken core journey, incorrect stage/cutoff behaviour or failed recovery without a safe workaround. Define the full severity matrix at the first gate. Every gate records artifact/version, evidence location, result and owner; an unchecked requirement remains open.

## Weekly delivery plan

The dated work sessions below each have an outcome and acceptance criterion. A calendar gate is a review of completed evidence, not a claim that the task has passed.

### Week 1 — 2026-10-26: Scope, evidence protection and release criteria

- **2026-10-27 — Scope the Windows 1.0 release (1.5h).** Define the forecast -> review -> score -> export journey, supported Windows version and product claims. Defer cloud, billing, engine migration and full UI redesign. Acceptance: Written must-have/deferred list and measurable release checklist.
- **2026-10-29 — Protect the frozen scientific runtime (1.5h).** Separate release development from pinned 2026 experiments before editing core files. Plan explicit scheduler routing and preserved source/input snapshots; do not blindly re-pin old cohorts. Acceptance: Release branch/runtime boundary recorded; frozen forecasts and receipts remain intact.
- **2026-10-31 — GATE: scope and release-risk register (3h).** Confirm a local-first Windows release, model-evidence policy, owner decisions, effort budget and top release risks. Review data rights and signing dependencies early. Acceptance: Kyle approves scope; no promise of new model promotion or calibrated probabilities without evidence.

### Week 2 — 2026-11-02: Provider access and distribution feasibility

- **2026-11-03 — Verify provider sign-in and recovery (1.5h).** Exercise FastF1 authentication, expired/missing credentials and restore flows in an isolated workspace. Confirm what users must supply themselves. Acceptance: A documented successful sign-in plus safe failure/recovery; no bundled credentials.
- **2026-11-05 — Harden offline and provider failure handling (1.5h).** Test cached use, network loss, 401/403, 429 and exhausted access. Bound retries and distinguish unavailable data from healthy/no-event observations. Acceptance: Visible actionable failures; cached results remain usable; no runaway retry loops.
- **2026-11-07 — GATE: data rights, licences and branding (3h).** Review code/dependency licences separately from underlying data, asset and branding rights. Decide distribution/commercial scope and signing budget. No purchases or public distribution are authorised by this calendar entry. Acceptance: Documented distribution basis and notices plan; unresolved rights/access blockers have an owner and stop public release.

### Week 3 — 2026-11-09: Data contracts and forecast correctness

- **2026-11-10 — Validate rosters, Q ranks and penalties (1.5h).** Build fixtures for complete/partial classifications, DNS/DQ/NC, driver substitutions and announced penalties. Preserve official Q order separately from later race-day grid changes. Acceptance: No fabricated ranks, lost entrants or silent team/driver join errors.
- **2026-11-12 — Test time cutoffs and Sprint state handling (1.5h).** Rehearse PRE/FP1/SQ/S/Q/R availability and standard weekends against published rules and feed state. Never substitute missing FP2 for an unsupported stage. Acceptance: Target-race outcomes cannot enter features; unavailable inputs remain explicit.
- **2026-11-14 — GATE: data-contract acceptance matrix (3h).** Run dry/wet, standard/Sprint, missing-data, interrupted-session and late-penalty scenarios. Retain evidence and input/source versions. Acceptance: All must-have correctness scenarios pass; failures cannot create misleading frozen forecasts.

### Week 4 — 2026-11-16: Usable forecast-to-score journey

- **2026-11-17 — Fix the core navigation and setup journey (1.5h).** Use the current desktop stack. Make forecast, results, comparison and scoring discoverable; distinguish current controls from the saved run being shown. Acceptance: One usable end-to-end workflow, without requiring the unapproved full design-playground rebuild.
- **2026-11-19 — Make assumptions and missing data legible (1.5h).** Expose roster/grid sources, feature age, uncertainty limits and unavailable prices/weather/strategy. Exercise keyboard, contrast, small-window and reduced-motion behaviour. Acceptance: No mock values presented as model evidence; core screens remain readable and operable.
- **2026-11-21 — GATE: task-based usability walkthrough (3h).** Rehearse a new user selecting an event, running a forecast, understanding results, scoring an old race and exporting evidence. Acceptance: Core tasks completed without undocumented developer steps; only release-relevant UX defects enter the backlog.

### Week 5 — 2026-11-23: Reliability, backup and recovery

- **2026-11-24 — Exercise interruption, cancellation and retry (1.5h).** Run repeated interrupted downloads/simulations, restart the app and verify safe resumption. Check deduplication and frozen-file protection. Acceptance: No corrupted committed runs, duplicate deliveries or silent partial success.
- **2026-11-26 — Rehearse backup, restore and upgrade (1.5h).** Restore a real saved forecast, evaluation and receipt into an isolated workspace. Test side-by-side upgrade/rollback without deleting existing user data. Acceptance: Recovered hashes match; settings and credentials stay local; rollback steps are documented.
- **2026-11-28 — GATE: reliability and recovery evidence (3h).** Complete a 20-scenario cached/failed-network regression pack, including restart and recovery. Investigate any data-loss or core-workflow failure. Acceptance: Zero open P0/P1 defects in the covered workflows; retained recovery receipts and logs.

### Week 6 — 2026-11-30: First clean-machine package and signing route

- **2026-12-01 — Build the first release-shaped Windows package (1.5h).** Create a uniquely named PyInstaller onedir/ZIP artifact from a recorded commit. Inspect runtime dependencies and absence of secrets, caches and personal archives. Acceptance: Package manifest and checksums; no overwrite of old releases; no Python/MATLAB/Node required for core use.
- **2026-12-03 — Choose signing and minimum-PC acceptance (1.5h).** Confirm signing/certificate or service route, cost approval and support policy. Define Windows 11 x64 test configurations and a warm-cache performance target on named hardware. Acceptance: Budget/owner decision recorded; signing not postponed to launch week.
- **2026-12-05 — GATE: clean Windows installation smoke (3h).** Run the actual package on a clean Windows VM/device. Test WebView2 detection/browser fallback, first launch, offline review, export and uninstall/side-by-side replacement. Acceptance: A non-developer machine runs the core product; source-test success is not substituted for packaged proof.

### Week 7 — 2026-12-07: 2026 evidence review and 2027 model policy

- **2026-12-08 — Audit completed 2026 shadow evidence (1.5h).** After the scheduled 6 December finale, count distinct scored races by cohort/stage. Recheck source/input/result provenance, missing stages and calibration coverage. Acceptance: A coverage ledger; seeds, stages and different cohorts are not inflated into independent race counts.
- **2026-12-10 — Compare accuracy and probability guardrails (1.5h).** Review paired finish loss, win/podium/top-10/DNF Brier, RPS and calibration. Isolate form contribution from degradation-only control and retirement prior. Acceptance: No retrospective diagnostic is relabelled fresh; insufficient evidence remains an explicit result.
- **2026-12-12 — GATE: decide 2027 model policy (3h).** Promote only where existing stage-specific fresh-evidence rules and explicit review are satisfied. Few 2026 races remain, so the plan must not depend on new candidates qualifying. Acceptance: Established defaults remain if gates fail; product claims stay honest. If that violates the agreed release promise, reduce scope or delay.

### Week 8 — 2026-12-14: Pilot preparation and holiday checkpoint

- **2026-12-15 — CONTINGENCY: close evidence-review blockers (1.5h).** Reserved capacity for the highest release blocker from the evidence review; if clear, strengthen a missing acceptance fixture. Acceptance: One prioritised issue closed or a documented blocker/owner/date; no new feature scope.
- **2026-12-17 — Prepare pilot scripts and support diagnostics (1.5h).** Define five core pilot tasks, a local redacted diagnostic bundle and issue template. Identify 3-5 willing pilot users; any outreach is Kyle-led, not an automatic invitation. Acceptance: Pilot checklist, support steps and safe logs ready; no secrets or central telemetry by default.
- **2026-12-19 — GATE: pilot-ready build and holiday handoff (3h).** Prepare a verified preview package and onboarding instructions. Record known issues, backups and what can run unattended over the break. Acceptance: No open P0/P1 in pilot core tasks; no planned project blocks from 21 December through 3 January.

### Week 9 — 2027-01-04: 2027 references and Sprint opener rehearsal

- **2027-01-05 — Verify official 2027 calendar and session rules (1.5h).** Recheck the official calendar, Sprint format and supported session-state transitions. Bahrain is currently the 12-14 March Sprint opener. Acceptance: Versioned official references; differences from 2026 are identified rather than assumed.
- **2027-01-07 — Refresh 2027 entry and reference contracts (1.5h).** Review published drivers, teams, venues, tyres and penalties. Preserve publication cutoffs. Fantasy features stay unavailable where official 2027 rules/prices are not yet verified. Acceptance: No invented entrants or 2026 rules silently presented as 2027 facts.
- **2027-01-09 — GATE: Bahrain Sprint opener replay (3h).** Use completed Sprint fixtures and the verified 2027 format to rehearse eligible inputs, scoring and missing-session behaviour. Do not require an FP2 that the schedule does not contain. Acceptance: The opener path works with explicit assumptions and no future-data leakage.

### Week 10 — 2027-01-11: Pilot and dependency decision

- **2027-01-12 — Run pilot onboarding and clean installs (1.5h).** Have the agreed pilot users execute the core tasks on their machines. Collect consented, redacted feedback; no bulk telemetry or automatic contact. Acceptance: At least three independent task-based pilot runs, or a documented recruitment blocker.
- **2027-01-14 — Triage pilot defects and performance (1.5h).** Prioritise crashes, wrong data, frozen-run failures and user confusion. Measure warm-cache runtime, memory and cancellation on declared hardware. Acceptance: Issue severity and reproducible evidence; observed performance replaces assumed performance.
- **2027-01-16 — GATE: pilot exit and dependency freeze (3h).** Close core pilot P0/P1s. Choose the tested FastF1/provider dependency version and lock all runtime dependencies; explicitly assess the currently pinned alpha risk. Acceptance: At least three users finish core tasks without developer intervention; dependency choice and fallbacks documented.

### Week 11 — 2027-01-18: Feature complete and operator documentation

- **2027-01-19 — Close high-impact accessibility and UX defects (1.5h).** Fix keyboard/focus, contrast, scaling and the highest pilot friction. Keep the existing desktop architecture and avoid cosmetic scope expansion. Acceptance: Core workflows usable on supported screen sizes and input methods.
- **2027-01-21 — Finish user, privacy and support documentation (1.5h).** Document account/access requirements, data locations, backup/restore, updates, known limitations and support process. Explain optional Discord and sharing controls. Acceptance: A new user can install, forecast, interpret, score and recover without private instructions.
- **2027-01-23 — GATE: feature complete and scope freeze (3h).** Freeze the v1.0 feature list. Remaining work is defects, security, packaging, acceptance and release operations. Acceptance: Any incomplete optional feature is cut or clearly disabled; no new engine, framework or cloud service.

### Week 12 — 2027-01-25: Security, provenance and release buffer

- **2027-01-26 — Review local API, secrets and file boundaries (1.5h).** Inspect local binding, browser/API protections, path validation, credential storage and log redaction. Check untrusted model/artifact handling. Acceptance: No unresolved high-severity exposure; optional external actions require user intent.
- **2027-01-28 — Complete dependency notices and build provenance (1.5h).** Create the release dependency inventory/SBOM and third-party notices; link the exact source commit, package checksums and approved data/branding decisions. Acceptance: Distribution evidence complete; raw archives, tokens and personal files are not shipped.
- **2027-01-30 — CONTINGENCY: close release-blocking defects (3h).** Three-hour buffer for the highest outstanding packaging, security or pilot blocker. If clear, repeat the weakest recovery test. Acceptance: No new scope; remaining blocker decisions are escalated before RC freeze.

### Week 13 — 2027-02-01: End-to-end release rehearsal

- **2027-02-02 — Run source regression and actual EXE acceptance (1.5h).** Run Python/JavaScript CI plus the packaged-EXE smoke and functional checks. Verify the binary contains the tested source changes. Acceptance: Source and packaged validation recorded separately; no stale dist folder treated as current.
- **2027-02-04 — Rehearse opener workflow and rollback (1.5h).** Exercise forecast -> freeze -> review -> safe export -> official scoring, with failure injection, correct timestamps and a rollback into an isolated workspace. Acceptance: Normal and Sprint fixtures pass; no upload without consent and no duplicate receipt delivery.
- **2027-02-06 — GATE: complete release rehearsal (3h).** Rehearse download, signature/checksum verification, clean install, upgrade, rollback and user support on the actual release path. Acceptance: Zero open release-blocking P0/P1s; recovery and support runbook demonstrated.

### Week 14 — 2027-02-08: Launch preparation and RC readiness

- **2027-02-09 — CONTINGENCY: remaining pilot and package fixes (1.5h).** Reserved 90 minutes for the highest residual defect. If clear, improve one unverified acceptance scenario. Acceptance: No discretionary new features; evidence gap closed or release risk explicitly recorded.
- **2027-02-11 — Prepare release notes and distribution draft (1.5h).** Draft the release/download page, supported-platform statement, known limitations and support policy. Keep publication behind the final release decision. Acceptance: Draft assets point to the intended signed package and accurate feature/model claims.
- **2027-02-13 — GATE: release-candidate readiness (3h).** Audit data access, rights, security, pilot acceptance, package compatibility, rollback and model policy before producing the frozen RC. Acceptance: All mandatory gates have evidence and owners; unresolved P0/P1 blocks RC approval.

### Week 15 — 2027-02-15: Release candidate freeze

- **2027-02-16 — Build and sign the release candidate (1.5h).** Build the uniquely versioned RC from a recorded commit; sign through the approved route and verify checksums/signatures on another supported machine. Acceptance: A reproducible signed artifact, manifests and test receipts; no private build-only dependency.
- **2027-02-18 — CONTINGENCY: final RC blockers (1.5h).** Reserved capacity to close the last critical defect or repeat an acceptance failure before the testing-week freeze. Acceptance: No gate waived for the deadline; use a new version for any rebuilt artifact.
- **2027-02-20 — GATE: freeze RC and model settings (3h).** Freeze the candidate artifact and model/calibration settings before Bahrain testing starts on 24 February. Record the 2027 challenger or established-model decision. Acceptance: Immutable version/provenance. Any later source fix creates a new candidate/version and reruns acceptance; never re-pin old forecasts.

### Week 16 — 2027-02-22: Pre-season live integration

- **2027-02-23 — Prepare testing-week data and monitoring checks (1.5h).** Verify provider access, calendar/session mapping, expected entrants and request limits before testing. Do not interpret testing as a race or fresh accuracy validation. Acceptance: An integration-only test checklist and safe failure/rollback path.
- **2027-02-25 — Smoke-test pre-season live data (1.5h).** During the published 24-27 February Bahrain test window, verify access, timestamps, driver/team identity and missing-data UI on the packaged build. Acceptance: New-season data loads or fails explicitly; no tuning or performance claims from test lap times.
- **2027-02-27 — GATE: testing integration and hotfix decision (3h).** Review testing-week compatibility. Permit only evidenced blocking fixes or versioned factual-reference updates; preserve frozen model/calibration policy. Acceptance: If changed, create a new RC/cohort and rerun relevant acceptance. Integration success is not accuracy proof.

### Week 17 — 2027-03-01: Release decision and production launch

- **2027-03-02 — CONTINGENCY: final evidence audit or blocker fix (1.5h).** Reserved 90 minutes to close a final blocker; otherwise audit every mandatory gate and ensure release notes match the actual build. Acceptance: One final candidate identity and a clear pass/hold recommendation.
- **2027-03-04 — GATE: final production go/no-go (1.5h).** Review the signed package, data/access rights, supported Windows checks, pilot results, restore/rollback, zero P0/P1s, security and honest model claims. Acceptance: Kyle explicitly approves the exact release or records a hold. A calendar entry never authorises publication by itself.
- **2027-03-06 — TARGET: production release or hold / rollback window (3h).** Target 6 March, six days before the currently scheduled first GP weekend. Publish only the explicitly approved artifact, verify the real download/clean install, and retain rollback capacity. Acceptance: Approved release verified end to end, or a documented hold. No unsupported model promotion or deadline-driven gate bypass.

## Launch decision and first-week support

- **20 February:** freeze the versioned release candidate and model settings. Any source fix produces a new candidate and repeats affected acceptance checks; preserve scientific provenance.
- **27 February:** testing integration review. Allow blocking fixes and verified factual updates; do not tune predictive parameters to testing laps.
- **4 March:** Kyle approves or rejects the exact release artifact against every mandatory gate. Approval includes the selected distribution/signing route and truthful product claims.
- **6 March:** conditional production release and rollback window. Verify the actual downloaded artifact and clean install after publication. If gates fail, record HOLD and the revised plan.
- **9 March:** post-release installation, recovery and support buffer (1.5h).
- **11 March:** final opener reference, access and scheduler readiness check (1.5h), before the Sprint weekend starts on 12 March.

The detailed personal calendar schedule and Outlook verification receipts are local-only under ignored `outputs/release_plan/20261024/`. They are not release evidence. This document changes no production code, live configuration, forecasts or scheduled tasks.
