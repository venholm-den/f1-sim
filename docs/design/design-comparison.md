# Concept comparison and recommendation

The scores below come from building every concept in the playground on the same mock data and comparing them screen by screen at 1440 px and 390 px. They are design judgements, not user-test results. A short test with three to five real users (see `implementation-roadmap.md`, phase 0) should confirm them before the build starts.

## Weighted scores (1–10)

| Criterion (weight) | A Pit Wall | B Lights Out | C Quant | D Grid | E Raceline | **H Hybrid** |
| --- | --- | --- | --- | --- | --- | --- |
| Data visualisation (25%) | 8 | 6 | 9 | 6 | 9 | **9** |
| Usability (20%) | 7 | 6 | 5 | 9 | 6 | **8** |
| Identity (15%) | 7 | 10 | 6 | 7 | 9 | **8** |
| Replay (15%) | 9 | 8 | 7 | 6 | 7 | **9** |
| Fantasy (10%) | 7 | 7 | 9 | 9 | 6 | **8** |
| Responsive (10%) | 5 | 7 | 4 | 10 | 7 | **8** |
| Feasibility (5%) | 8 | 6 | 7 | 7 | 4 | **6** |
| **Weighted total** | **7.40** | **7.10** | **6.85** | **7.50** | **7.35** | **8.30** |

The hybrid's scores are a projection. It is built and clickable in the playground, but its responsive layouts have had less tuning than D's.

## Why each concept scored as it did

- **A Pit Wall.**
  - Strengths: it has the best replay, because every panel follows one playhead. It is close to today's look.
  - Weaknesses: tables lead, so casual users get no answers, and its mobile layout is just the desktop panels stacked.
- **B Lights Out.**
  - Strengths: the identity is unmistakable, and the broadcast stage makes a great replay showpiece.
  - Weaknesses: always-on team colours make the 22-line charts noisy, and analysis screens feel bolted on.
- **C Quant.**
  - Strengths: it has the richest Fantasy optimisation (value frontier, locks) and the densest prediction views.
  - Weaknesses: it is the hardest to learn, all-monospace text is tiring, and it is unusable on a phone.
- **D Grid.**
  - Strengths: it is the clearest for newcomers, the best on mobile, and its Fantasy flow is easy to follow.
  - Weaknesses: depth is hidden behind disclosures, the replay is weak, and the look is generic.
- **E Raceline.**
  - Strengths: it explains uncertainty better than anything else, through the futures, the dots and the river.
  - Weaknesses: it is slow for repeat use, it needs truthful copy for every weekend, and it is the most work to build.

## Recommendation: the hybrid (H)

**What it takes from each concept:**

- **A** contributes the frame: the dark tiled workspace, timing-colour semantics, keyboard map, shared driver focus and one replay playhead.
- **D** contributes an answer row at the top of every screen and "Show the maths" disclosures. This fixes the audit's top problem, that answers are buried.
- **E** contributes the signature charts: quantile dots, fifty futures and the river with event pins. These make uncertainty visible without gauges.
- **C** contributes signed deltas everywhere, plus the value frontier as an optional view in Fantasy.
- **B** contributes nothing structural. Its broadcast tower styling could become a "presentation mode" for sharing screenshots later.

**Why not D alone.** D scores well for usability, but Race Workbench's distinctive value is the model's depth: replay, the lab and evaluation. D hides that depth. The hybrid keeps D's answers on top and the depth underneath.

**Why not A alone.** A is the safest migration, but it still leads with tables, and that is the main usability complaint.

**Risks of the hybrid.**

1. The answer row needs rules so its sentences are always computed from data and never hand-written.
2. Fifty futures needs stored per-simulation orders. If a run keeps only the position matrix, the orders must be sampled from it and labelled "approximate".
3. Mobile still needs dedicated layouts for replay and Fantasy, which is more work than in D.

**Decision needed from Kyle.** Choose one of: H (recommended), A, D, or "another mix". No production code changes until a direction is picked.

## Update: Kyle prefers B's look

Kyle picked **B (Lights Out)** as his favourite look. To keep the hybrid's usability and chart fixes, the playground now has a variant called **L · Broadcast hybrid** (`?c=l`). L applies B's visual identity to the hybrid's screens:

- **From B:** the red-ruled top bar, skewed kickers, Barlow Condensed caps, white position blocks and a lower-third story bar.
- **From the hybrid:** the answer rows, fifty futures, quantile dots and the pinned river.
- **Fixes to B's weaknesses:**
  - The full-height hero is cut to a slim strip, which saves about 170 px of height at 1440 × 900.
  - The analysis screens (lab, accuracy, drivers) use the hybrid's panel layouts instead of B's feature cards, so they no longer feel bolted on.
- **Still open:** the race river colours every driver by team, as it does in B and H, so 22 lines remain busy until a driver is focused. Dimming unfocused lines by default is a candidate change for production.

| Criterion (weight) | B Lights Out | H Hybrid | **L Broadcast hybrid (projected)** |
| --- | --- | --- | --- |
| Data visualisation (25%) | 6 | 9 | **8** |
| Usability (20%) | 6 | 8 | **7** |
| Identity (15%) | 10 | 8 | **10** |
| Replay (15%) | 8 | 9 | **9** |
| Fantasy (10%) | 7 | 8 | **8** |
| Responsive (10%) | 7 | 8 | **7** |
| Feasibility (5%) | 6 | 6 | **5** |
| **Weighted total** | **7.10** | **8.30** | **8.00** |

L scores data visualisation and usability one point below H because the condensed capitals are slower to read in dense tables. For that reason, body text stays in Barlow at normal case. L's feasibility is lower because the broadcast detailing (skewed shapes, clip-paths, team stripes) is extra CSS to maintain. If L is confirmed, the roadmap is unchanged. Only phase 1 changes, to use B's tokens and bundle Barlow and Barlow Condensed locally.
