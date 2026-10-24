# Design playground

An isolated, clickable prototype of the five redesign concepts and the recommended hybrid. **It is not part of the app.** PyInstaller only bundles `portable_app/web`, and nothing here is imported by production code.

**All numbers are mock data.** They come from a seeded toy Monte Carlo in `mock-data.js`, covering the 2026 grid, a mock US Grand Prix (R19, 56 laps, safety car on laps 24–26), and mock season form and evaluation. Team colours are approximate. Every screen shows a "Mock data" tag.

## Run it

```bash
cd design/playground
python -m http.server 8765
# open http://localhost:8765/
```

Opening `index.html` directly also works in Chromium-based browsers. Fonts load from Google Fonts; the production plan bundles them locally (see `docs/design/design-system.md`).

## What you can do

- **Shell (`index.html`)**: switch concept (A–E, Hybrid ★, and Broadcast hybrid ◆: B's look on the hybrid's screens) and screen (Weekend, Predict, Fantasy, Replay, Drivers, Lab, Accuracy).
  - Views: desktop · mobile (390 × 844) · desktop + mobile · side by side (pick a second concept) · all five.
  - Keys: `[` and `]` change the screen, `,` and `.` change the concept, `M` cycles the view.
  - The URL keeps the state: `?c=h&s=replay&v=both`.
- **Inside a concept (`frame.html?c=a&s=replay`)**:
  - Click a driver to focus them, Shift-click to compare two, Esc to clear.
  - `1`–`7` switch screen.
  - On replay: `Space` plays, `←`/`→` step a lap, `Home`/`End` jump to the start or finish.
  - Fantasy chips cycle lock in → leave out → auto, and the optimiser re-picks the team.
  - Lab sliders re-run the toy simulation.
  - Concept C has a command line: type a screen (`PRED`, `FANT`, `RPLY`), one or two driver codes, or `LAP 30`.
  - `prefers-reduced-motion` is respected.

## Files

| File | Purpose |
| --- | --- |
| `index.html` | Comparison shell |
| `frame.html`, `frame.js` | One concept on one screen; shared interactions |
| `mock-data.js` | Seeded mock data and toy simulator |
| `charts.js` | SVG chart registry (range, dots, heat, bump, tyres, scatter, track, ridge, futures, …) |
| `blocks.js` | Shared building blocks (tables, Fantasy optimiser, replay tower, lab) |
| `concept-*.js`, `concepts.css` | One render function per screen per concept, plus each concept's tokens |
| `base.css` | Shared chart and accessibility styles |
