from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class OutputFile:
    label: str
    path: str
    exists: bool
    size_bytes: int


CORE_OUTPUTS = [
    ("Simulation Summary", "simulation_summary.csv"),
    ("Position Matrix", "position_matrix.csv"),
    ("Driver Model Features", "driver_model_features.csv"),
    ("Reliability Profile", "debug/reliability_profile.csv"),
    ("Tyre Strategy", "strategy/predicted_tyre_strategy.csv"),
    ("History Adjusted Strategy", "strategy/predicted_tyre_strategy_history_adjusted.csv"),
    ("Race Dashboard", "report/race_dashboard.png"),
    ("Tyre Strategy Timeline", "report/tyre_strategy_timeline.png"),
    ("Fantasy Risk Reward", "report/fantasy_risk_reward.png"),
    ("Model Commentary", "report/model_commentary.txt"),
]


def list_core_outputs(output_dir: str | Path) -> list[OutputFile]:
    root = Path(output_dir)
    files: list[OutputFile] = []

    for label, relative_path in CORE_OUTPUTS:
        path = root / relative_path
        files.append(
            OutputFile(
                label=label,
                path=str(path),
                exists=path.exists(),
                size_bytes=path.stat().st_size if path.exists() else 0,
            )
        )

    return files


def read_output_table(output_dir: str | Path, relative_path: str, max_rows: int = 100) -> pd.DataFrame:
    path = Path(output_dir) / relative_path

    if not path.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(path, nrows=max_rows)
    except Exception:
        return pd.DataFrame()

