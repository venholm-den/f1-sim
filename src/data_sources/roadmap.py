from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data_sources.fia_documents import (
    FIA_DOCUMENT_INDEX_PATH,
    ensure_fia_document_index,
)
from src.data_sources.openf1 import OPENF1_ENDPOINTS


def build_data_source_roadmap() -> pd.DataFrame:
    rows = []

    rows.extend(
        [
            {
                "source": "OpenF1",
                "data": "Live positions",
                "status": "module scaffolded",
                "target_module": "src/grid.py, src/report_card.py, src/simulation_viz.py",
                "notes": "Use latest row per driver from /position.",
            },
            {
                "source": "OpenF1",
                "data": "Intervals and gaps",
                "status": "module scaffolded",
                "target_module": "src/report_card.py, src/simulation_viz.py",
                "notes": "Use /intervals for live gap context.",
            },
            {
                "source": "OpenF1",
                "data": "Pit events",
                "status": "module scaffolded",
                "target_module": "src/strategy.py, src/report_card.py",
                "notes": "Use /pit to update live strategy and stop timing.",
            },
            {
                "source": "OpenF1",
                "data": "Stints",
                "status": "module scaffolded",
                "target_module": "src/strategy.py, src/tyres.py",
                "notes": "Use /stints for compounds, stint numbers and tyre age.",
            },
            {
                "source": "OpenF1",
                "data": "Race control events",
                "status": "module scaffolded",
                "target_module": "src/weather.py, src/simulate.py, src/report_card.py",
                "notes": "Use /race_control for safety car, red flag, yellow flag and incident context.",
            },
            {
                "source": "FIA documents",
                "data": "Official grids",
                "status": "local CSV integration scaffolded",
                "target_module": "src/grid.py",
                "notes": "Feed official starting grid and penalty-adjusted grid into grid_position.",
            },
            {
                "source": "FIA documents",
                "data": "Penalties",
                "status": "local CSV integration scaffolded",
                "target_module": "src/grid.py, src/strategy.py, src/report_card.py",
                "notes": "Use grid penalties and steward decisions to correct assumptions.",
            },
            {
                "source": "FIA documents",
                "data": "Summons",
                "status": "local CSV integration scaffolded",
                "target_module": "src/report_card.py",
                "notes": "Surface relevant official notes in reports.",
            },
            {
                "source": "FIA documents",
                "data": "Classifications",
                "status": "local CSV integration scaffolded",
                "target_module": "src/backtest.py",
                "notes": "Use official classification as backtest fallback or cross-check.",
            },
        ]
    )

    return pd.DataFrame(rows)


def save_data_source_roadmap(
    output_dir: str = "outputs/data_sources",
) -> str:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    roadmap = build_data_source_roadmap()
    file_path = output_path / "data_source_roadmap.csv"
    roadmap.to_csv(file_path, index=False)

    ensure_fia_document_index(FIA_DOCUMENT_INDEX_PATH)

    return str(file_path)


def describe_openf1_endpoints() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "endpoint": endpoint.name,
                "path": endpoint.path,
                "purpose": endpoint.purpose,
            }
            for endpoint in OPENF1_ENDPOINTS.values()
        ]
    )