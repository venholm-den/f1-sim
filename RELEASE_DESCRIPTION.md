# v0.2.1

This release formalizes the hybrid architecture for `f1-sim` and adds the Python-to-Rust handoff needed for a faster packaged runtime.

## Highlights

- Documented the project architecture split:
  - Python: FastF1 data collection, ML model training, race simulation prototype, CSV/JSON generation, data reports, and Power BI prep.
  - Rust: high-speed simulation engine, packaged backend, and portable desktop app runtime.
  - React/Tauri: user interface, charts, race setup screens, export buttons, and desktop wrapper.
- Added the Python exporter for Rust-ready model inputs:

```powershell
python scripts/export_rust_model_inputs.py --year 2026 --event Monaco --session Q --output outputs\rust\model_inputs.json
```

- Added architecture documentation at `docs/architecture.md`.
- Updated development commands to show the Python-to-Rust model-input workflow.

## Rust Runtime Path

The companion Rust runtime consumes the exported model input JSON:

```powershell
cargo run -- simulate --config config/default_run_config.json --model-inputs ..\f1-sim\outputs\rust\model_inputs.json
```

## Notes

- Python remains the source of truth for data collection, feature engineering, reports, Power BI prep, and model training.
- Rust should consume Python-generated model inputs rather than duplicate FastF1 or model-training logic.
- The future packaged UI direction is React/TypeScript inside a Tauri/Rust desktop wrapper.
