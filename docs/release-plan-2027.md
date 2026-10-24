# 2027 subscription product release plan

Revised 24 October 2026 to reflect the desktop/mobile subscription product. This supersedes the Windows-only scope. Owner: Kyle; Codex supports implementation and evidence gathering.

## Product direction and staged delivery

The long-term product is desktop and native mobile apps with subscription access to approved forecasts generated on Kyle's PC, personal simulations, optional personal Discord delivery, user-authorised historical downloads and Fantasy analysis.

**6 March 2027 is a conditional paid-pilot target**, covering Windows desktop, hosted published forecasts, customer accounts/subscriptions, mobile-friendly companion, local personal simulations, manually saved Fantasy teams and optional Discord. It is not a promise of native iOS/Android, hosted personal simulation jobs or automatic Fantasy account synchronisation by March. The [official calendar](https://www.formula1.com/en/racing/2027) should be rechecked in January and before the opener; retain the existing 20 February RC freeze, 27 February integration review and 4 March go/no-go.

Native iOS/Android and hosted personal jobs follow measured pilot results, with dates estimated only after capacity/cost and platform feasibility checks. Automatic Fantasy sync requires permitted access; manual team entry remains the fallback. A full UI/engine rewrite is outside this pilot.

## Architecture and data boundaries

| Component | Responsibility |
| --- | --- |
| Producer PC | Run approved models in a protected scientific runtime; validate/freeze results; publish outbound with narrowly scoped credentials. No direct public customer access to the home PC. |
| Hosted service | Store versioned forecasts; serve authenticated/entitled clients; manage app identity, subscriptions and private preferences. Remain useful with explicit freshness labels when the producer is offline. |
| Desktop | Read published forecasts, run personal scenarios locally, use browser-based personal provider authentication and retain historical archives locally. Never upload F1 passwords or archives by default. |
| Mobile companion | Responsive access to published forecasts, subscription status and saved preferences/teams. Verify on real mobile browsers. |
| Later native/mobile execution | Native clients and bounded queued simulations on separate workers; benchmark costs, cancellation, concurrency and isolation before committing allowances. The producer PC is not the promised paid on-demand compute service. |

Published forecasts carry model version, stage, input cutoff, generation/publication time and provenance. Personal scenarios show changed assumptions and cannot overwrite official results or enter official performance records. User data and Discord destinations are private per account. Desktop-only posting and hosted posting while the desktop is closed are separate capabilities; the pilot must state which is delivered.

## Commercial and integration feasibility

Start with one paid-tier hypothesis and test value and willingness to pay before setting prices. Define cancellation, renewal, failed-payment, expiry and purchase recovery behaviour. Sandbox first; production charging, purchases, outreach, service changes and publication require their own explicit decisions. Avoid unlimited hosted compute commitments.

Customer F1 access is separate from this app subscription. A user's authenticated access does not establish rights to commercial derived-output publication, raw-data redistribution or account integration. Review each intended use early and retain evidence. Unresolved rights block the affected feature or commercial release.

The [published Fantasy terms](https://fantasy.formula1.com/en/terms) restrict automated extraction and commercial exploitation. Do not promise automatic account/team sync without a permitted route. Advisory recommendations and manually saved teams are the initial scope; do not automatically make transfers.

Native mobile billing requires platform/storefront review, not a blanket assumption that web checkout suffices: [Apple guidelines](https://developer.apple.com/app-store/review/guidelines/) and [Google Play payments policy](https://support.google.com/googleplay/android-developer/answer/10281818?hl=en). Recheck these before native implementation. Budget applicable consumer/privacy/tax decisions and support obligations without treating draft policies as proof of compliance.

## Capacity, model evidence and stop conditions

Keep 17 six-hour active weeks (102h) plus 3h pre-opener support: **105 hours total**, with 21 December–3 January clear. Nine pre-release contingency hours remain embedded on 15 December, 30 January, 9 February, 18 February and 2 March. These are timeboxes, not reliable estimates that a larger commercial scope will fit. At every Saturday review re-estimate remaining work, cut optional scope or move the pilot; do not remove verification to protect the date.

Preserve existing four-model and independent form/risk cohorts, frozen forecasts, inputs and delivery receipts. Keep PRE/FP2/Q separate. Consult [accuracy improvements](accuracy-improvements.md) and [prospective trials](prospective-prediction-trials.md). Promotion gates are at least six fresh distinct races per requested stage, at least 5% paired RPS improvement (threshold RPS for prospective trials, which store win/podium/top-10 chances only), no finish MAE or Brier regression, Q beating qualifying order, and explicit review. Kyle switched the primary metric from the MAE-dominated loss to RPS on 24 October 2026; see [promotion lanes](promotion-lanes-and-challenger.md). No inflated race counts or historical diagnostics relabelled prospective evidence. Retain the established model if evidence is insufficient. Testing laps verify integration, not prediction accuracy. A verified model means one that passed a documented process, not guaranteed accuracy.

## Mandatory paid-pilot acceptance

- Approved scope, price/value hypothesis, distribution/data/branding basis and measured hosting/support assumptions.
- PC outbound publication is atomic, validated, versioned and safe to retry. PC outages retain the last valid snapshot with visible freshness.
- Customer authentication, per-user isolation and server-verified entitlements pass; payment events are authenticated and idempotent. Cancellation, expiry, failure and restoration pass.
- Source tests and actual packaged-client/service acceptance are recorded separately. Clean supported Windows installation and real-phone browser core journeys pass.
- At least three independent pilot users complete the core journey without developer intervention. Demand/value evidence informs whether to charge.
- Normal/Sprint cutoffs and missing-data handling are correct; personal scenarios and official forecasts stay distinct. Provider sign-in and recovery are verified without centralising provider credentials.
- Backup, restore, rollback, secret handling, redacted diagnostics, dependency notices/build provenance and user-facing support/privacy/subscription policies are demonstrated against the actual release.
- No unresolved P0/P1 defects. P0 includes data loss, exposed secrets or unusable service; P1 includes broken customer access/core journey, incorrect stage/cutoff behaviour or recovery without a safe workaround.

Each gate records exact versions, evidence location, owner and pass/hold decision. Unresolved commercial permissions, security, billing/access, model claims or recovery failures mean HOLD or a reduced private/non-paid pilot. Model promotion is never an automatic consequence of release scheduling.

## Dated delivery sessions

### Week 1: Product scope and commercial feasibility

- **2026-10-27 — Define subscription MVP and staged mobile scope (1.5h).** Specify desktop local sims, PC-produced published forecasts, hosted accounts/subscriptions and a mobile-friendly companion. Native iOS/Android, hosted personal jobs and automatic Fantasy sync follow the pilot. Acceptance: Approved feature/claim matrix, pilot audience and cut list; no all-platform launch promise.
- **2026-10-29 — Check commercial data and Fantasy integration permissions (1.5h).** Investigate provider access, commercial derived-output publication, branding and Fantasy import permissions. Identify an authorised route or manual-entry fallback. Acceptance: Evidence and owner for each rights question; unresolved rights block affected commercial features.
- **2026-10-31 — GATE: architecture, capacity and paid-pilot scope (3h).** Map PC outbound publishing to hosted storage/API and desktop/mobile clients. Define subscription value, success measures, budget decisions and protected scientific runtime. Acceptance: One agreed architecture and 105-hour budget; preserve frozen cohorts, forecasts and receipts.

### Week 2: Publishing contracts and scientific isolation

- **2026-11-03 — Define immutable forecast publication contract (1.5h).** Specify model version, stage, input cutoff, generation/publication times, provenance, checksum and visibility. Keep official forecasts separate from personal scenarios. Acceptance: Versioned schema and example accepted/rejected payloads.
- **2026-11-05 — Protect forecasting runtime and publisher credentials (1.5h).** Design a stable scientific runtime separate from commercial development; use scoped outbound publisher credentials with explicit scheduler routing. Acceptance: No inbound customer access to home PC; no task changes or re-pinning existing cohorts without a separate decision.
- **2026-11-07 — GATE: publishing and stale-data failure rehearsal (3h).** Rehearse atomic publication, duplicate/retry handling, failed validation and PC offline states using fixtures. Acceptance: Previous approved forecast stays available; stale/failed runs are labelled and do not overwrite healthy publication.

### Week 3: Hosted foundation and customer identity

- **2026-11-10 — Build minimal hosted forecast storage and read API (1.5h).** Implement authorised retrieval, versioned snapshots, atomic latest pointers and a minimal service deployment draft. Acceptance: Fixture clients read permitted forecasts; raw archives and user secrets excluded.
- **2026-11-12 — Add customer identity and private data separation (1.5h).** Implement account/session boundaries, secret handling and per-user preferences; distinguish app account from provider account. Acceptance: Cross-user access denied and session expiry/recovery tested.
- **2026-11-14 — GATE: end-to-end PC-to-client publishing slice (3h).** Exercise PC-generated fixture -> validated publication -> authenticated desktop/mobile-sized reader. Acceptance: Same version/provenance shown across clients; account isolation and offline freshness behaviour pass.

### Week 4: Subscription product and sandbox billing

- **2026-11-17 — Define paid value, pricing experiment and usage limits (1.5h).** Identify target customers, ongoing paid value, proposed monthly/annual options and support costs. Avoid unlimited hosted compute promises. Acceptance: Pricing hypothesis, cost assumptions and willingness-to-pay pilot questions; price remains provisional.
- **2026-11-19 — Integrate checkout sandbox and entitlement records (1.5h).** Implement hosted checkout draft, verified payment events and idempotent entitlement updates; never trust a client paid flag. Acceptance: Sandbox subscription activates exactly once; invalid/replayed events cannot grant access.
- **2026-11-21 — GATE: cancellation, renewal and purchase recovery (3h).** Exercise active, failed payment, cancelled, expired and restored subscriptions plus account recovery. Document mobile store billing review for later native launch. Acceptance: Cross-device entitlement states consistent; cancellation/access rules clear; no live charges.

### Week 5: Desktop local simulations and provider access

- **2026-11-24 — Separate official forecasts from My simulations (1.5h).** Expose local scenario controls and saved runs; label altered assumptions and prevent personal runs entering official accuracy records. Acceptance: Personal simulation cannot overwrite published forecasts or validated model policy.
- **2026-11-26 — Verify personal F1 sign-in and historical downloads (1.5h).** Exercise browser sign-in, access eligibility, expiry and recovery locally. Keep provider credentials/archive on the user's desktop. Acceptance: Real download and safe failure verified; no F1 password or personal archive uploaded to hosted service.
- **2026-11-28 — GATE: recovery, cutoff and Sprint correctness (3h).** Run core scenarios across PRE/FP2/Q, Sprint/missing sessions, interrupted local jobs and restore/upgrade. Acceptance: No future-data leakage, fabricated stages or damaged frozen outputs; release-blocking defects recorded.

### Week 6: Early packages and mobile companion

- **2026-12-01 — Build desktop package and responsive companion slice (1.5h).** Package existing desktop engine and connect both clients to hosted forecasts and app sign-in. Avoid an engine/framework rewrite. Acceptance: Recorded source/artifact hashes; usable core screens on desktop and phone-sized viewport.
- **2026-12-03 — Decide signing, hosting costs and minimum hardware (1.5h).** Choose supportable deployment/signing route, Windows test hardware, hosting budget and rollback ownership. Acceptance: Owner/cost decisions recorded; no purchases or production deployment implied by work block.
- **2026-12-05 — GATE: clean Windows and real-phone walkthrough (3h).** Test actual package without developer runtimes and the responsive companion on real mobile browsers, including sign-in and subscription status. Acceptance: Install/read/local-sim journey passes on supported desktop; published forecast readable on phone.

### Week 7: Evidence review and publication policy

- **2026-12-08 — Audit completed 2026 cohorts and stage coverage (1.5h).** Count fresh distinct scored races by stage/cohort and verify provenance. Do not inflate samples with seeds or merge experiments. Acceptance: Coverage ledger distinguishes historical diagnostics from prospective evidence.
- **2026-12-10 — Evaluate models and publishable performance claims (1.5h).** Review paired loss, Brier, distribution scores and calibration with matched baselines; separate form, wear and risk effects. Acceptance: No unsupported accuracy/verification claim; insufficient fresh evidence remains explicit.
- **2026-12-12 — GATE: select 2027 published model and fallback (3h).** Apply the promotion rules: six fresh races per requested stage, >=5% paired RPS improvement, no finish MAE or Brier regression, Q beats qualifying order and explicit review. Acceptance: Established model retained where gates fail; publication claims and subscription promise remain defensible.

### Week 8: Discord, Fantasy fallback and pilot preparation

- **2026-12-15 — CONTINGENCY: close commercial feasibility blockers (1.5h).** Reserve 90 minutes for the highest rights, publishing, billing or package blocker. Acceptance: One prioritised gap closed or explicit owner/hold decision; no new scope.
- **2026-12-17 — Prepare personal Discord and saved Fantasy team (1.5h).** Add explicit destination/preview/enable/disconnect and deduplicated delivery design; save manually entered team, bank and transfers per user. Acceptance: No cross-user webhook exposure; no automatic Fantasy scraping/account sync without authorised access.
- **2026-12-19 — GATE: pilot-ready commercial journey and holiday handoff (3h).** Review account -> sandbox subscription -> forecast -> personal sim -> saved team -> optional Discord. Prepare redacted diagnostics and five pilot tasks. Acceptance: Pilot candidate and instructions ready; no critical defects; 21 December-3 January clear.

### Week 9: 2027 reference data and cross-device preferences

- **2027-01-05 — Recheck official 2027 calendar and Sprint rules (1.5h).** Verify published season/session definitions and stage availability before changing reference data. Acceptance: Versioned official sources; missing FP2 stays unavailable rather than invented.
- **2027-01-07 — Refresh entrants and Fantasy rules; test user sync (1.5h).** Update only published 2027 facts; synchronise manual team/preferences with timestamp/conflict handling. Disable unverified prices/rules. Acceptance: No stale 2026 facts presented as current; users cannot read each other's teams.
- **2027-01-09 — GATE: opener rehearsal across desktop and mobile (3h).** Rehearse standard/Sprint fixtures through publishing, entitlements, saved team and desktop scenarios. Acceptance: Consistent forecast version and explicit missing/stale inputs on both clients.

### Week 10: Paid-product pilot and demand validation

- **2027-01-12 — Run three-user desktop and mobile pilot (1.5h).** With agreed testers, exercise onboarding, sandbox purchase, published forecast, local sim and recovery; collect consented redacted feedback. Acceptance: At least three independent task runs or documented recruitment blocker; no automatic outreach.
- **2027-01-14 — Assess willingness to pay and operating economics (1.5h).** Review user value, proposed price, support load, hosting/storage/payment assumptions and measured simulation cost. Acceptance: Evidence-based price/scope proposal; no invented customer demand or unlimited-compute commitment.
- **2027-01-16 — GATE: pilot exit, dependency freeze and commercial decision (3h).** Resolve core P0/P1s, choose tested provider/runtime pins and decide whether March paid pilot is justified. Acceptance: Three users finish core tasks; rights and value gaps cause scope cut/hold rather than unproven paid launch.

### Week 11: Feature complete and customer policies

- **2027-01-19 — Close desktop/mobile usability and accessibility gaps (1.5h).** Fix top pilot issues, keyboard/focus, touch controls, readable uncertainty and saved-run settings. Acceptance: Core tasks pass on supported desktop and mobile browsers without developer help.
- **2027-01-21 — Document privacy, subscriptions, support and recovery (1.5h).** Draft clear renewal/cancellation/refund process, local/cloud data boundaries, account deletion/export and support/rollback instructions; assess applicable commercial obligations. Acceptance: Customer-facing policies match actual behaviour; deletion process protects required records and respects retention decisions.
- **2027-01-23 — GATE: commercial MVP feature freeze (3h).** Freeze desktop + hosted forecasts + subscriptions + mobile companion + manual Fantasy + optional Discord scope. Acceptance: Cut incomplete optional scope; native apps, hosted personal jobs and authorised Fantasy sync remain a later roadmap.

### Week 12: Security, notices and contingency

- **2027-01-26 — Review hosted authorisation, payments and secret boundaries (1.5h).** Check cross-user reads/writes, session expiry, webhook verification, local API/file access, credentials and redaction. Acceptance: No unresolved high-severity exposure or shared customer/provider credentials.
- **2027-01-28 — Complete build provenance, notices and operations runbook (1.5h).** Record dependencies/SBOM, approved data/branding basis, artifact hashes, backups and hosted restore/credential rotation procedures. Acceptance: Traceable packages/service versions and demonstrated safe diagnostics; no raw archives bundled.
- **2027-01-30 — CONTINGENCY: highest commercial release blocker (3h).** Reserve three hours for the largest security, billing, rights, installation or pilot gap. Acceptance: No added features; explicit hold where evidence cannot be completed.

### Week 13: Commercial end-to-end rehearsal

- **2027-02-02 — Run source, packaged-client and service acceptance (1.5h).** Verify tests and actual binary separately; include subscription state transitions, API authorisation and publication failures. Acceptance: Recorded version-specific evidence; no stale executable counted as current.
- **2027-02-04 — Rehearse PC outage, restore and subscriber recovery (1.5h).** Exercise PC offline, failed publish, hosted backup restore, retry/dedup and account/purchase recovery. Acceptance: Last valid forecasts remain accessible with freshness labels; no duplicate Discord delivery.
- **2027-02-06 — GATE: full desktop/mobile commercial rehearsal (3h).** Rehearse download -> account -> sandbox subscription -> forecast -> desktop scenario -> Fantasy -> optional Discord -> cancellation/restore. Acceptance: Zero open P0/P1; real-device checks and operations recovery demonstrated.

### Week 14: Launch preparation and native-mobile next stage

- **2027-02-09 — CONTINGENCY: close pilot, billing or package gaps (1.5h).** Reserve 90 minutes for highest remaining blocker; otherwise strengthen weakest acceptance evidence. Acceptance: Scope stays frozen; evidence gap closed or explicit hold.
- **2027-02-11 — Prepare paid-pilot release assets and follow-on mobile backlog (1.5h).** Draft price/value explanation, setup/download/support and known limits. Define native iOS/Android, store billing and hosted job proof-of-concept acceptance for after pilot. Acceptance: Drafts reflect delivered scope; no native app availability or Fantasy account sync promised.
- **2027-02-13 — GATE: commercial release-candidate readiness (3h).** Audit rights, model claims, entitlements, security, clean-machine/mobile pilot, billing recovery and costs. Acceptance: Every mandatory requirement has evidence/owner; unresolved commercial blockers stop paid pilot.

### Week 15: Commercial release candidate

- **2027-02-16 — Build signed desktop RC and version hosted/mobile companion (1.5h).** Build immutable client artifact and pinned service/frontend versions; validate signing and checkout configuration in sandbox. Acceptance: Manifest identifies exact client/service/schema/model versions and rollback path.
- **2027-02-18 — CONTINGENCY: final commercial RC blockers (1.5h).** Reserve 90 minutes for blocking fixes and repeated acceptance before freeze. Acceptance: New candidate/version for rebuilt artifacts; no weakened model or commercial gates.
- **2027-02-20 — GATE: freeze RC, published model and entitlements (3h).** Freeze release candidate, model policy and subscription access behaviour before pre-season integration. Acceptance: Immutable provenance; later changes create new candidates and rerun affected checks.

### Week 16: Pre-season publishing integration

- **2027-02-23 — Prepare live access and publication monitoring (1.5h).** Check provider eligibility, reference identities, outbound publishing and stale-feed alerts on the candidate. Acceptance: Safe integration checklist; users never depend on direct home-PC access.
- **2027-02-25 — Verify new-season data through PC and both clients (1.5h).** Exercise actual available testing data -> validated publication -> entitled desktop/mobile reader; test explicit missing-data states. Acceptance: Correct identities/timestamps; testing laps do not establish model accuracy or justify tuning.
- **2027-02-27 — GATE: integration compatibility and hotfix decision (3h).** Review live compatibility and subscription/customer operations; permit only blocking fixes or verified factual references. Acceptance: New RC for changes; no last-minute model promotion, native rewrite or unauthorised Fantasy sync.

### Week 17: Conditional commercial pilot launch

- **2027-03-02 — CONTINGENCY: final release and commercial evidence audit (1.5h).** Reserve 90 minutes for exact-artifact audit of rights, security, billing, claims, costs and recovery. Acceptance: One clear release/hold recommendation with evidence and owner.
- **2027-03-04 — GATE: paid-pilot go/no-go and explicit launch approval (1.5h).** Review approved distribution/data basis, real-device acceptance, pilot demand, subscription lifecycle, support and exact artifact/service versions. Acceptance: Kyle approves exact paid pilot and any live payment/deployment actions, or records HOLD.
- **2027-03-06 — TARGET: desktop and mobile-companion paid pilot or HOLD (3h).** Release only the approved desktop/service/mobile companion; verify actual download, access and authorised payment path; retain rollback. Acceptance: Commercial journey verified end to end or HOLD. Native mobile and hosted personal sims follow measured pilot results.

## Pre-opener support and later stages

- **2027-03-09:** Review subscriber access, payment/restore issues, desktop installs and publishing freshness; use rollback if required. Acceptance: Usable service or explicit incident/hold; no new features.
- **2027-03-11:** Verify provider access, 2027 references, PC publication, subscription access, mobile freshness and read-only scheduler eligibility. Acceptance: Opener ready or explicit incident; preserve model policy and delivery receipts.

After the paid pilot, use observed demand and support/compute costs to size native-mobile work: choose the client approach through a device proof of concept; verify store billing/entitlement restore and review requirements; build bounded hosted jobs with cancellation and per-user isolation; repeat native-device acceptance before store submission. Investigate authorised Fantasy integration independently and keep manual entry until permitted. Do not assign extra hours or release dates to these stages without a revised capacity decision.

The detailed personal calendar and Outlook receipts remain local-only under ignored `outputs/release_plan/20261024/`. Calendar sessions schedule work; they do not execute services, deploy code, charge customers or invite testers. No production code, model settings, frozen forecasts or scheduled tasks change as part of this planning update.
