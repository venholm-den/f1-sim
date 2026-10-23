# Architecture

The current application uses Python for collection, feature engineering,
Monte Carlo simulation, reporting, automation, and the desktop backend. The
interface is HTML/CSS/JavaScript hosted in pywebview or the loopback browser
server. Managed child processes execute both Race Setup and Simulation Centre
jobs. MATLAB/Simulink is an optional validation workbench.

Rust and React/Tauri describe a possible future architecture and the separate
Rust integration contract; they do not power this checkout's desktop launcher.
The sections below distinguish that proposed ownership from today's runtime.

## Ownership

| Layer | Owns |
| --- | --- |
| Python | FastF1 data collection, ML model training, race simulation prototype, CSV/JSON generation, data reports, Power BI prep |
| MATLAB/Simulink | optional lap-level dynamics, strategy experiments, assumption inspection, engineering validation |
| Rust (proposed / separate repository) | high-speed simulation engine and future packaged backend |
| HTML/JavaScript + pywebview (current) | user interface and desktop wrapper |
| React/Tauri (proposed) | possible future UI and desktop wrapper |

## Python Responsibilities

Python handles workflows that benefit from the mature data-science ecosystem:

- FastF1 and related F1 data collection.
- Feature engineering and model-ready driver frames.
- Historical model training and calibration.
- Race simulation prototyping while model assumptions are changing.
- CSV/JSON generation for downstream tools.
- Report generation and chart/image assets.
- Power BI prep and data shaping.

The main runtime bridge to Rust is:

```powershell
python scripts/export_rust_model_inputs.py --year 2026 --event Monaco --session Q --output outputs\rust\model_inputs.json
```

## Rust Responsibilities

Rust handles workflows that benefit from speed, portability, and a stable typed runtime:

- High-speed Monte Carlo simulation engine.
- Stable input/output validation around the shared model-input contract.
- Packaged backend commands for the desktop app.
- Portable `.exe` app runtime and release artifacts.

Rust should consume Python-generated model inputs rather than duplicate FastF1 collection or model-training logic.

## React/Tauri Responsibilities

The portable desktop app should move toward a React/Tauri shell:

- React/TypeScript owns the user interface, charts, setup forms, tables, and export controls.
- Tauri/Rust owns the desktop wrapper and invokes Rust backend commands.
- Python remains available for data collection, model training, report generation, and data export workflows.

## Data Flow

```text
FastF1/OpenF1 + local CSV data
        |
        v
Python feature engineering, model training, calibration, reports
        |
        +---------------------> MATLAB/Simulink lap-dynamics validation
        |                              |
        |                              v
        |                     lap detail, strategy comparison, plots
        v
outputs/rust/model_inputs.json
        |
        v
Rust high-speed simulation engine
        |
        v
simulation summaries, snapshots, strategy candidates
        |
        v
Python reports / Power BI prep / React-Tauri desktop UI
```

## Contract

The Rust repo defines the model-input JSON schema:

```text
f1-sim-rust/schemas/model_inputs.schema.json
```

This Python repo exports that contract via:

```text
scripts/export_rust_model_inputs.py
```

The contract keeps the boundary simple: Python creates model-ready inputs, Rust runs fast simulations, and either side can consume the resulting CSV/JSON outputs.

The optional Simulink boundary follows the same rule. Python exports
`outputs/matlab/lap_dynamics_inputs.csv`; Simulink consumes it without owning
FastF1 collection or feature engineering. See [MATLAB and Simulink
validation](matlab-simulink.md).
