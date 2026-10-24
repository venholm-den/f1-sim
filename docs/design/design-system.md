# Design system (for the recommended hybrid)

This is the system the hybrid direction would ship with. It is written so it can drop into `portable_app/web/app.css` as CSS custom properties, replacing the Nocturne tokens gradually. Nothing here is applied to production yet.

## 1. Tokens

### Colour

| Token | HEX | Use | Contrast on `--panel` |
| --- | --- | --- | --- |
| `--bg` | `#0D0F13` | App background | — |
| `--panel` | `#14171D` | Panels and cards | — |
| `--panel-2` | `#1B1F26` | Raised rows, inputs | — |
| `--line` | `#272C35` | Borders | — |
| `--grid` | `#1E232B` | Chart gridlines | — |
| `--fg` | `#ECEEF1` | Primary text | 15.4 : 1 |
| `--muted` | `#97A0AD` | Labels, captions | 6.8 : 1 |
| `--accent` | `#FFB800` | Caution, safety car, primary action | 10.3 : 1 |
| `--select` | `#5AA9FF` | Selection, focus ring, links | 7.3 : 1 |
| `--pos` | `#2BD47D` | Improvement, gain | 9.2 : 1 |
| `--neg` | `#FF6166` | Loss, retirement | 6.1 : 1 |
| `--best` | `#B36BFF` | Best overall (timing purple) | 5.5 : 1 |
| `--tyre-s` / `-m` / `-h` | `#FF3B3B` / `#FFD12E` / `#EDEDED` | Compounds (always paired with the S/M/H letter) | — |

**Rules.**

- Team colours appear only on data marks (lines, dots, stripes), never on text or as panel fills. Each team's second driver is drawn dashed.
- Meaning colours (`--pos`, `--neg`, `--best`, `--accent`) always come with a sign, icon or letter (`+0.3`, `▲`, `S`). Nothing relies on colour alone.
- Red is not the brand colour. The brand is the amber accent plus the RW mark, which resolves the red overload noted in the audit.

**Contrast of the other concepts' text colours, for reference** (all computed in WCAG 2.1 against each concept's panel colour):

- A: muted 5.9; accent 10.5.
- B: brand red `#FF1E3C` 4.9, which is fine for large text only.
- C: muted 5.4.
- D: the accent fill `#FF3D2E` is 3.5 (below AA for text), so D uses `#C8261A` (5.6) for text.
- E: the vermilion fill is 3.5, so E uses `#B13F1A` (5.6) for text. The safety-car ochre `#C98A00` is 2.8 and is used only as a band fill, never for text.

### Spacing, radius, elevation

- Spacing scale: 4 · 8 · 12 · 16 · 24 · 32 px. Panels use 12 px padding, and the gap between panels is 8 px.
- Radius: 6 px for panels and 4 px for chips. Bars have square ends, because rounded ends misstate the value.
- Elevation: none. Hierarchy comes from `--panel` and `--panel-2`, plus a 1 px `--line`.

### Typography

| Role | Font | Size / weight |
| --- | --- | --- |
| Answer value | Inter Tight | 22 px / 700 |
| Panel title | Inter Tight | 11 px / 600, uppercase, +0.08em |
| Body | Inter Tight | 13–14 px / 400–500 |
| Numbers (everywhere) | JetBrains Mono | `font-variant-numeric: tabular-nums` |
| Chart labels | JetBrains Mono | 11 px |

**Local font bundling (required for the offline app).** The playground loads Google Fonts for convenience. Production must bundle the WOFF2 files: Inter Tight (400, 500, 600 and 700, plus the variable font) and JetBrains Mono (400 and 600). Put them in `portable_app/web/fonts/` with `@font-face` rules and `font-display: swap`. They are about 300 KB in total, and both fonts are under the SIL Open Font License. The fallback stack is `system-ui, "Segoe UI"` and `ui-monospace, Consolas`.

## 2. Components

| Component | Anatomy | States |
| --- | --- | --- |
| **App bar** | RW mark · event (round, name) · tabs 1–7 · forecast status · mock/candidate tag | Tab hover, current (`aria-current="page"`) |
| **Answer row** | 4 tiles, each with label · value · one-line qualifier | Loading (skeleton text), unavailable ("—" plus the reason) |
| **Panel** | Header (title, meta) · body · optional "Show the maths" disclosure | Default, focused-driver context, empty |
| **Timing tower** | Position · team stripe · code · gap · tyre letter and age | Focused, retired (strikethrough + DNF), in pit |
| **Data table** | Sticky first column, right-aligned numbers, units in the header | Row hover, row focus via Enter |
| **Market chip** | Code · price | Auto, locked (amber border + 🔒 text "locked"), excluded (struck through + "out") |
| **Transport** | ⏮ · play/pause · ⏭ · scrubber · lap readout · speed | Playing, paused, at the end |
| **Flag chip** | Green / SC / VSC / Red label | Uses text as well as colour |
| **Footer key strip** | Key hints · current focus | — |
| **Badges** | `MOCK`, `CANDIDATE`, `UNCALIBRATED`, `FROZEN` | Always text, never icon-only |

## 3. Chart style

- **Grid:** 1 px gridlines in `--grid`. Axes have no tick marks, and labels are in `--muted`.
- **Encoding:** quantitative values use position or length first, area only for secondary variables (price, count), and never angle.
- **Baselines:** bars always start at zero. Position axes are inverted so that P1 is at the top.
- **Labels:** label data marks directly where possible. When a legend is unavoidable, it sits at the top-left in the same order as the marks.
- **Focus:** non-focused marks drop to 25% opacity. A focused mark gets a 2 px stroke and a label.
- **Uncertainty:** shown by default as a P10–P90 line plus a P25–P75 bar plus a P50 tick. Single numbers are always accompanied by their range or by a sentence ("but someone else wins 69% of the time").
- **Tooltips:** values with units and the sample size ("31.2% · 10,000 races").
- **Empty and error states:** a sentence in the chart area saying why it is empty (for example, "Telemetry unavailable for this lap"), never a blank box.

## 4. Accessibility

- **Contrast:** text meets WCAG 2.1 AA, and large numbers meet AAA in the hybrid (see the table above).
- **Not colour alone:** tyre letters, ▲/▼ signs, flag words and line dashes back up every colour cue.
- **Keyboard:**
  - Every interactive control can be reached with Tab.
  - Charts expose their marks as focusable `[data-driver]` groups, and Enter focuses the driver.
  - The replay keys work whenever focus is not inside a text field.
- **Screen readers:**
  - Each chart has `role="img"` and an `aria-label` sentence, plus a "View as table" disclosure.
  - The replay lap readout is an `aria-live="polite"` region, updated at most once per second while playing.
- **Motion:** `prefers-reduced-motion: reduce` removes easing, staggering and flashes. Playback still works but jumps lap by lap.
- **Targets:** at least 32 px on desktop and 44 px on touch.
- **Zoom:** layouts reflow without horizontal scrolling up to 200% zoom at 1280 px. Wide tables scroll inside their own panel.

## 5. Responsive breakpoints

| Width | Layout |
| --- | --- |
| ≥ 1280 px | Full named-area grid (panels side by side) |
| 900–1279 px | Two columns; telemetry and the alternatives tables drop below |
| < 900 px | Single column in priority order: answers → main chart → table. Tabs become a scrollable strip |
| < 480 px | Answer row becomes a 2 × 2 grid. Tables show 3 columns and the rest go behind "More" |
