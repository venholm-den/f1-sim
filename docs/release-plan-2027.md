# 2027 free pilot release plan

Revised 24 October 2026 to reflect the desktop/mobile product, and again on 29 October 2026 when Kyle dropped paid plans for 2027 (see [Rights and the no-charge decision](#rights-and-the-no-charge-decision)). This supersedes the Windows-only scope and the earlier paid-pilot target. Owner: Kyle; Codex supports implementation and evidence gathering.

## Product direction and staged delivery

The long-term product is desktop and native mobile apps with account access to approved forecasts generated on Kyle's PC, personal simulations, optional personal Discord delivery, user-authorised historical downloads and Fantasy analysis.

**6 March 2027 is a conditional free, invite-only pilot target**, covering Windows desktop, hosted published forecasts, invite-only accounts, mobile-friendly companion, local personal simulations, manually saved Fantasy teams and optional Discord. It is not a promise of native iOS/Android, hosted personal simulation jobs or automatic Fantasy account synchronisation by March. The [official calendar](https://www.formula1.com/en/racing/2027) should be rechecked in January and before the opener; retain the existing 20 February RC freeze, 27 February integration review and 4 March go/no-go. Nothing is charged in 2027: no subscriptions, checkout or payments.

Native iOS/Android and hosted personal jobs follow measured pilot results, with dates estimated only after capacity/cost and platform feasibility checks. Automatic Fantasy sync requires permitted access; manual team entry remains the fallback. A full UI/engine rewrite is outside this pilot.

## Architecture and data boundaries

| Component | Responsibility |
| --- | --- |
| Producer PC | Run approved models in a protected scientific runtime; validate/freeze results; publish outbound with narrowly scoped credentials. No direct public customer access to the home PC. |
| Hosted service | Store versioned forecasts; serve authenticated, invited clients; manage app identity, invite-only access and private preferences. Remain useful with explicit freshness labels when the producer is offline. |
| Desktop | Read published forecasts, run personal scenarios locally, use browser-based personal provider authentication and retain historical archives locally. Never upload F1 passwords or archives by default. |
| Mobile companion | Responsive access to published forecasts, account status and saved preferences/teams. Verify on real mobile browsers. |
| Later native/mobile execution | Native clients and bounded queued simulations on separate workers; benchmark costs, cancellation, concurrency and isolation before committing allowances. The producer PC is not an on-demand compute service for users. |

Published forecasts carry model version, stage, input cutoff, generation/publication time and provenance. Personal scenarios show changed assumptions and cannot overwrite official results or enter official performance records. User data and Discord destinations are private per account. Desktop-only posting and hosted posting while the desktop is closed are separate capabilities; the pilot must state which is delivered.

## Rights and the no-charge decision

On 29 October 2026 Kyle decided there are no paid plans in 2027. The pilot and any wider 2027 release are free. Any future paid plan needs its own explicit decision and a confirmed data basis first.

Why: Formula 1's terms limit its content, including timing data, to personal, non-commercial use. F1 Help (case 02316748, 29 October 2026) could not answer licensing questions and pointed to brandprotection@f1.com, which only reviews full commercial licensing proposals with proposed fees or royalties. No proposal was sent. Jolpica (CC BY-NC-SA, commercial use needs approval) and Open-Meteo (free tier is non-commercial) also fit a free product but not a paid one without further agreement.

What this means:

- No subscriptions, checkout, payment events, entitlements or prices. Access is by invite and app account only.
- Keep the product non-commercial: no adverts, sponsorship or paid tiers. Donations or tips need their own decision because they may still count as commercial use.
- Keep attribution for Jolpica (CC BY-NC-SA) and Open-Meteo (CC BY 4.0), no F1 logos or branding, and a clear notice that the app is unofficial and not associated with Formula 1.
- A user's own F1 access is separate from this app account. A user's authenticated access does not establish rights to derived-output publication, raw-data redistribution or account integration. Raw timing data is never redistributed.

The [published Fantasy terms](https://fantasy.formula1.com/en/terms) restrict automated extraction and commercial exploitation. Do not promise automatic account/team sync without a permitted route. Advisory recommendations and manually saved teams are the initial scope; do not automatically make transfers.

Native mobile apps still need platform/storefront review: [Apple guidelines](https://developer.apple.com/app-store/review/guidelines/) and [Google Play policies](https://support.google.com/googleplay/android-developer/answer/10281818?hl=en). Recheck these before native implementation. Budget applicable privacy decisions and support obligations without treating draft policies as proof of compliance.

## Capacity, model evidence and stop conditions

Keep 17 six-hour active weeks (102h) plus 3h pre-opener support: **105 hours total**, with 21 December–3 January clear. Nine pre-release contingency hours remain embedded on 15 December, 30 January, 9 February, 18 February and 2 March. These are timeboxes, not reliable estimates that a larger scope will fit. At every Saturday review re-estimate remaining work, cut optional scope or move the pilot; do not remove verification to protect the date.

Preserve existing four-model and independent form/risk cohorts, frozen forecasts, inputs and delivery receipts. Keep PRE/FP2/Q separate. Consult [accuracy improvements](accuracy-improvements.md) and [prospective trials](prospective-prediction-trials.md). Promotion gates are at least six fresh distinct races per requested stage, at least 5% paired RPS improvement (threshold RPS for prospective trials, which store win/podium/top-10 chances only), no Brier regression, finish MAE no worse beyond noise, Q beating qualifying order, and explicit review. Kyle switched the primary metric from the MAE-dominated loss to RPS on 24 October 2026; see [promotion lanes](promotion-lanes-and-challenger.md). No inflated race counts or historical diagnostics relabelled prospective evidence. Retain the established model if evidence is insufficient. Testing laps verify integration, not prediction accuracy. A verified model means one that passed a documented process, not guaranteed accuracy.

## Mandatory pilot acceptance

- Approved scope, value hypothesis, non-commercial distribution/data/branding basis and measured hosting/support assumptions.
- PC outbound publication is atomic, validated, versioned and safe to retry. PC outages retain the last valid snapshot with visible freshness.
- Account authentication, per-user isolation and server-verified invite access pass. Revoking an invite, account recovery and account deletion pass. No payment flow exists.
- Source tests and actual packaged-client/service acceptance are recorded separately. Clean supported Windows installation and real-phone browser core journeys pass.
- At least three independent pilot users complete the core journey without developer intervention. Value evidence informs whether the pilot continues and what a later release keeps.
- Normal/Sprint cutoffs and missing-data handling are correct; personal scenarios and official forecasts stay distinct. Provider sign-in and recovery are verified without centralising provider credentials.
- Backup, restore, rollback, secret handling, redacted diagnostics, dependency notices/build provenance and user-facing support/privacy/access policies are demonstrated against the actual release.
- No unresolved P0/P1 defects. P0 includes data loss, exposed secrets or unusable service; P1 includes broken user access/core journey, incorrect stage/cutoff behaviour or recovery without a safe workaround.

Each gate records exact versions, evidence location, owner and pass/hold decision. Unresolved data permissions, security, access, model claims or recovery failures mean HOLD or a reduced private pilot. Model promotion is never an automatic consequence of release scheduling.

## Dated delivery sessions

### Week 1: Product scope and rights

- **2026-10-27 — Define pilot MVP and staged mobile scope (1.5h).** Specify desktop local sims, PC-produced published forecasts, hosted accounts and a mobile-friendly companion. Native iOS/Android, hosted personal jobs and automatic Fantasy sync follow the pilot. Acceptance: Approved feature/claim matrix, pilot audience and cut list; no all-platform launch promise.
- **2026-10-29 — Check data and Fantasy integration permissions (1.5h).** Investigate provider access, derived-output publication, branding and Fantasy import permissions. Identify an authorised route or manual-entry fallback. Acceptance: Evidence and owner for each rights question; unresolved rights block affected features. Outcome: no commercial basis for F1 timing data, so Kyle dropped paid plans for 2027.
- **2026-10-31 — GATE: architecture, capacity and pilot scope (3h).** Map PC outbound publishing to hosted storage/API and desktop/mobile clients. Define pilot value, success measures, budget decisions and protected scientific runtime. Acceptance: One agreed architecture and 105-hour budget; preserve frozen cohorts, forecasts and receipts.

### Week 2: Publishing contracts and scientific isolation

- **2026-11-03 — Define immutable forecast publication contract (1.5h).** Specify model version, stage, input cutoff, generation/publication times, provenance, checksum and visibility. Keep official forecasts separate from personal scenarios. Acceptance: Versioned schema and example accepted/rejected payloads.
- **2026-11-05 — Protect forecasting runtime and publisher credentials (1.5h).** Design a stable scientific runtime separate from product development; use scoped outbound publisher credentials with explicit scheduler routing. Acceptance: No inbound user access to home PC; no task changes or re-pinning existing cohorts without a separate decision.
- **2026-11-07 — GATE: publishing and stale-data failure rehearsal (3h).** Rehearse atomic publication, duplicate/retry handling, failed validation and PC offline states using fixtures. Acceptance: Previous approved forecast stays available; stale/failed runs are labelled and do not overwrite healthy publication.

### Week 3: Hosted foundation and user identity

- **2026-11-10 — Build minimal hosted forecast storage and read API (1.5h).** Implement authorised retrieval, versioned snapshots, atomic latest pointers and a minimal service deployment draft. Acceptance: Fixture clients read permitted forecasts; raw archives and user secrets excluded.
- **2026-11-12 — Add customer identity and private data separation (1.5h).** Implement account/session boundaries, secret handling and per-user preferences; distinguish app account from provider account. Acceptance: Cross-user access denied and session expiry/recovery tested.
- **2026-11-14 — GATE: end-to-end PC-to-client publishing slice (3h).** Exercise PC-generated fixture -> validated publication -> authenticated desktop/mobile-sized reader. Acceptance: Same version/provenance shown across clients; account isolation and offline freshness behaviour pass.

### Week 4: Invite-only access and pilot measures

- **2026-11-17 — Define pilot value, success measures and usage limits (1.5h).** Identify target users, what keeps them coming back each race weekend and support costs. Avoid unlimited hosted compute promises. Acceptance: Value hypothesis, cost assumptions and pilot questions; no prices or paid tiers.
- **2026-11-19 — Add invite-only access records (1.5h).** Implement a server-side invite list and access records; never trust a client flag. Acceptance: An invited account gets access exactly once; uninvited, revoked or replayed invites cannot grant access.
- **2026-11-21 — GATE: invite, revoke, deletion and account recovery (3h).** Exercise invited, revoked, deleted and restored accounts plus account recovery. Acceptance: Cross-device access states consistent; access rules clear; no payment flow.

### Week 5: Desktop local simulations and provider access

- **2026-11-24 — Separate official forecasts from My simulations (1.5h).** Expose local scenario controls and saved runs; label altered assumptions and prevent personal runs entering official accuracy records. Acceptance: Personal simulation cannot overwrite published forecasts or validated model policy.
- **2026-11-26 — Verify personal F1 sign-in and historical downloads (1.5h).** Exercise browser sign-in, access eligibility, expiry and recovery locally. Keep provider credentials/archive on the user's desktop. Acceptance: Real download and safe failure verified; no F1 password or personal archive uploaded to hosted service.
- **2026-11-28 — GATE: recovery, cutoff and Sprint correctness (3h).** Run core scenarios across PRE/FP2/Q, Sprint/missing sessions, interrupted local jobs and restore/upgrade. Acceptance: No future-data leakage, fabricated stages or damaged frozen outputs; release-blocking defects recorded.

### Week 6: Early packages and mobile companion

- **2026-12-01 — Build desktop package and responsive companion slice (1.5h).** Package existing desktop engine and connect both clients to hosted forecasts and app sign-in. Avoid an engine/framework rewrite. Acceptance: Recorded source/artifact hashes; usable core screens on desktop and phone-sized viewport.
- **2026-12-03 — Decide signing, hosting costs and minimum hardware (1.5h).** Choose supportable deployment/signing route, Windows test hardware, hosting budget and rollback ownership. Acceptance: Owner/cost decisions recorded; no purchases or production deployment implied by work block.
- **2026-12-05 — GATE: clean Windows and real-phone walkthrough (3h).** Test actual package without developer runtimes and the responsive companion on real mobile browsers, including sign-in and account status. Acceptance: Install/read/local-sim journey passes on supported desktop; published forecast readable on phone.

### Week 7: Evidence review and publication policy

- **2026-12-08 — Audit completed 2026 cohorts and stage coverage (1.5h).** Count fresh distinct scored races by stage/cohort and verify provenance. Do not inflate samples with seeds or merge experiments. Acceptance: Coverage ledger distinguishes historical diagnostics from prospective evidence.
- **2026-12-10 — Evaluate models and publishable performance claims (1.5h).** Review paired loss, Brier, distribution scores and calibration with matched baselines; separate form, wear and risk effects. Acceptance: No unsupported accuracy/verification claim; insufficient fresh evidence remains explicit.
- **2026-12-12 — GATE: select 2027 published model and fallback (3h).** Apply the promotion rules: six fresh races per requested stage, >=5% paired RPS improvement, no Brier regression, finish MAE no worse beyond noise, Q beats qualifying order and explicit review. Acceptance: Established model retained where gates fail; publication claims remain defensible.

### Week 8: Discord, Fantasy fallback and pilot preparation

- **2026-12-15 — CONTINGENCY: close pilot feasibility blockers (1.5h).** Reserve 90 minutes for the highest rights, publishing, access or package blocker. Acceptance: One prioritised gap closed or explicit owner/hold decision; no new scope.
- **2026-12-17 — Prepare personal Discord and saved Fantasy team (1.5h).** Add explicit destination/preview/enable/disconnect and deduplicated delivery design; save manually entered team, bank and transfers per user. Acceptance: No cross-user webhook exposure; no automatic Fantasy scraping/account sync without authorised access.
- **2026-12-19 — GATE: pilot-ready journey and holiday handoff (3h).** Review invite -> account -> forecast -> personal sim -> saved team -> optional Discord. Prepare redacted diagnostics and five pilot tasks. Acceptance: Pilot candidate and instructions ready; no critical defects; 21 December-3 January clear.

### Week 9: 2027 reference data and cross-device preferences

- **2027-01-05 — Recheck official 2027 calendar and Sprint rules (1.5h).** Verify published season/session definitions and stage availability before changing reference data. Acceptance: Versioned official sources; missing FP2 stays unavailable rather than invented.
- **2027-01-07 — Refresh entrants and Fantasy rules; test user sync (1.5h).** Update only published 2027 facts; synchronise manual team/preferences with timestamp/conflict handling. Disable unverified prices/rules. Acceptance: No stale 2026 facts presented as current; users cannot read each other's teams.
- **2027-01-09 — GATE: opener rehearsal across desktop and mobile (3h).** Rehearse standard/Sprint fixtures through publishing, invite access, saved team and desktop scenarios. Acceptance: Consistent forecast version and explicit missing/stale inputs on both clients.

### Week 10: Pilot and value validation

- **2027-01-12 — Run three-user desktop and mobile pilot (1.5h).** With agreed testers, exercise invite and onboarding, published forecast, local sim and recovery; collect consented redacted feedback. Acceptance: At least three independent task runs or documented recruitment blocker; no automatic outreach.
- **2027-01-14 — Assess pilot value and running costs (1.5h).** Review user value, support load, hosting/storage assumptions and measured simulation cost, since Kyle pays the running costs with no revenue. Acceptance: Evidence-based scope proposal and cost ceiling; no invented demand or unlimited-compute commitment.
- **2027-01-16 — GATE: pilot exit, dependency freeze and release decision (3h).** Resolve core P0/P1s, choose tested provider/runtime pins and decide whether the March free pilot is justified and how many invites it has. Acceptance: Three users finish core tasks; rights and value gaps cause scope cut/hold rather than an unproven release.

### Week 11: Feature complete and user policies

- **2027-01-19 — Close desktop/mobile usability and accessibility gaps (1.5h).** Fix top pilot issues, keyboard/focus, touch controls, readable uncertainty and saved-run settings. Acceptance: Core tasks pass on supported desktop and mobile browsers without developer help.
- **2027-01-21 — Document privacy, access, support and recovery (1.5h).** Draft invite/revocation rules, the unofficial and non-commercial notice, attributions, local/cloud data boundaries, account deletion/export and support/rollback instructions. Acceptance: User-facing policies match actual behaviour; deletion process protects required records and respects retention decisions.
- **2027-01-23 — GATE: pilot MVP feature freeze (3h).** Freeze desktop + hosted forecasts + invite-only accounts + mobile companion + manual Fantasy + optional Discord scope. Acceptance: Cut incomplete optional scope; native apps, hosted personal jobs and authorised Fantasy sync remain a later roadmap.

### Week 12: Security, notices and contingency

- **2027-01-26 — Review hosted authorisation and secret boundaries (1.5h).** Check cross-user reads/writes, session expiry, invite handling, local API/file access, credentials and redaction. Acceptance: No unresolved high-severity exposure or shared user/provider credentials.
- **2027-01-28 — Complete build provenance, notices and operations runbook (1.5h).** Record dependencies/SBOM, approved data/branding basis, artifact hashes, backups and hosted restore/credential rotation procedures. Acceptance: Traceable packages/service versions and demonstrated safe diagnostics; no raw archives bundled.
- **2027-01-30 — CONTINGENCY: highest release blocker (3h).** Reserve three hours for the largest security, access, rights, installation or pilot gap. Acceptance: No added features; explicit hold where evidence cannot be completed.

### Week 13: End-to-end rehearsal

- **2027-02-02 — Run source, packaged-client and service acceptance (1.5h).** Verify tests and actual binary separately; include invite access state changes, API authorisation and publication failures. Acceptance: Recorded version-specific evidence; no stale executable counted as current.
- **2027-02-04 — Rehearse PC outage, restore and user recovery (1.5h).** Exercise PC offline, failed publish, hosted backup restore, retry/dedup and account recovery. Acceptance: Last valid forecasts remain accessible with freshness labels; no duplicate Discord delivery.
- **2027-02-06 — GATE: full desktop/mobile rehearsal (3h).** Rehearse download -> invite -> account -> forecast -> desktop scenario -> Fantasy -> optional Discord -> revoke/restore. Acceptance: Zero open P0/P1; real-device checks and operations recovery demonstrated.

### Week 14: Launch preparation and native-mobile next stage

- **2027-02-09 — CONTINGENCY: close pilot, access or package gaps (1.5h).** Reserve 90 minutes for highest remaining blocker; otherwise strengthen weakest acceptance evidence. Acceptance: Scope stays frozen; evidence gap closed or explicit hold.
- **2027-02-11 — Prepare pilot release assets and follow-on mobile backlog (1.5h).** Draft value explanation, unofficial/non-commercial notice, setup/download/support and known limits. Define native iOS/Android and hosted job proof-of-concept acceptance for after pilot. Acceptance: Drafts reflect delivered scope; no native app availability or Fantasy account sync promised.
- **2027-02-13 — GATE: release-candidate readiness (3h).** Audit rights, model claims, invite access, security, clean-machine/mobile pilot, account recovery and costs. Acceptance: Every mandatory requirement has evidence/owner; unresolved blockers stop the pilot.

### Week 15: Release candidate

- **2027-02-16 — Build signed desktop RC and version hosted/mobile companion (1.5h).** Build immutable client artifact and pinned service/frontend versions; validate signing configuration. Acceptance: Manifest identifies exact client/service/schema/model versions and rollback path.
- **2027-02-18 — CONTINGENCY: final RC blockers (1.5h).** Reserve 90 minutes for blocking fixes and repeated acceptance before freeze. Acceptance: New candidate/version for rebuilt artifacts; no weakened model or release gates.
- **2027-02-20 — GATE: freeze RC, published model and access rules (3h).** Freeze release candidate, model policy and invite access behaviour before pre-season integration. Acceptance: Immutable provenance; later changes create new candidates and rerun affected checks.

### Week 16: Pre-season publishing integration

- **2027-02-23 — Prepare live access and publication monitoring (1.5h).** Check provider eligibility, reference identities, outbound publishing and stale-feed alerts on the candidate. Acceptance: Safe integration checklist; users never depend on direct home-PC access.
- **2027-02-25 — Verify new-season data through PC and both clients (1.5h).** Exercise actual available testing data -> validated publication -> invited desktop/mobile reader; test explicit missing-data states. Acceptance: Correct identities/timestamps; testing laps do not establish model accuracy or justify tuning.
- **2027-02-27 — GATE: integration compatibility and hotfix decision (3h).** Review live compatibility and user operations; permit only blocking fixes or verified factual references. Acceptance: New RC for changes; no last-minute model promotion, native rewrite or unauthorised Fantasy sync.

### Week 17: Conditional free pilot launch

- **2027-03-02 — CONTINGENCY: final release evidence audit (1.5h).** Reserve 90 minutes for exact-artifact audit of rights, security, access, claims, costs and recovery. Acceptance: One clear release/hold recommendation with evidence and owner.
- **2027-03-04 — GATE: free pilot go/no-go and explicit launch approval (1.5h).** Review non-commercial distribution/data basis, real-device acceptance, pilot demand, invite list, support and exact artifact/service versions. Acceptance: Kyle approves the exact pilot, its invites and any deployment actions, or records HOLD.
- **2027-03-06 — TARGET: desktop and mobile-companion free pilot or HOLD (3h).** Release only the approved desktop/service/mobile companion to invited users; verify actual download and access; retain rollback. Acceptance: Pilot journey verified end to end or HOLD. Native mobile and hosted personal sims follow measured pilot results.

## Pre-opener support and later stages

- **2027-03-09:** Review user access, account recovery issues, desktop installs and publishing freshness; use rollback if required. Acceptance: Usable service or explicit incident/hold; no new features.
- **2027-03-11:** Verify provider access, 2027 references, PC publication, invite access, mobile freshness and read-only scheduler eligibility. Acceptance: Opener ready or explicit incident; preserve model policy and delivery receipts.

After the pilot, use observed demand and support/compute costs to size native-mobile work: choose the client approach through a device proof of concept; verify store review requirements; build bounded hosted jobs with cancellation and per-user isolation; repeat native-device acceptance before store submission. Investigate authorised Fantasy integration independently and keep manual entry until permitted. Do not assign extra hours or release dates to these stages without a revised capacity decision. Paid plans are not on the roadmap; revisiting them needs a confirmed licence for F1 data and a new decision from Kyle.

The detailed personal calendar and Outlook receipts remain local-only under ignored `outputs/release_plan/20261024/`. Calendar sessions schedule work; they do not execute services, deploy code or invite testers. No production code, model settings, frozen forecasts or scheduled tasks change as part of this planning update.
