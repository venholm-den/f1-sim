from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
import threading

import pandas as pd


@dataclass(frozen=True)
class OutputFile:
    label: str
    path: str
    exists: bool
    size_bytes: int


CORE_OUTPUTS = [
    ("Simulation Summary", "simulation_summary.csv"),
    ("Prediction Reasoning", "prediction_reasoning.csv"),
    ("Position Matrix", "position_matrix.csv"),
    ("Driver Model Features", "driver_model_features.csv"),
    ("Reliability Profile", "debug/reliability_profile.csv"),
    ("Tyre Strategy", "strategy/predicted_tyre_strategy.csv"),
    ("History Adjusted Strategy", "strategy/predicted_tyre_strategy_history_adjusted.csv"),
    ("Race Dashboard", "report/race_dashboard.png"),
    ("Tyre Strategy Timeline", "report/tyre_strategy_timeline.png"),
    ("Fantasy Risk Reward", "report/fantasy_risk_reward.png"),
    ("Season Points Projection", "season/latest_season_projection.png"),
    ("Season Projection Data", "season/latest_season_projection.csv"),
    ("Model Commentary", "report/model_commentary.txt"),
]

def list_core_outputs(output_dir: str | Path) -> list[OutputFile]:
    return _list_outputs(output_dir, CORE_OUTPUTS)


def _list_outputs(output_dir: str | Path, outputs: list[tuple[str, str]]) -> list[OutputFile]:
    root = Path(output_dir)
    files: list[OutputFile] = []

    for label, relative_path in outputs:
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


# One outputs() call reads the same lap table from several helpers, so keep
# the last few bounded reads keyed by file identity and hand out copies.
_TABLE_CACHE: OrderedDict = OrderedDict()
_TABLE_CACHE_LOCK = threading.Lock()
_TABLE_CACHE_SIZE = 8


def read_output_table(output_dir: str | Path, relative_path: str, max_rows: int | None = 100) -> pd.DataFrame:
    path = Path(output_dir) / relative_path

    try:
        info = path.stat()
    except OSError:
        return pd.DataFrame()
    key = (str(path.resolve()), info.st_mtime_ns, info.st_size, max_rows)
    if max_rows is not None:
        with _TABLE_CACHE_LOCK:
            cached = _TABLE_CACHE.get(key)
            if cached is not None:
                _TABLE_CACHE.move_to_end(key)
                return cached.copy()

    try:
        table = pd.read_csv(path, nrows=max_rows)
    except Exception:
        return pd.DataFrame()
    if max_rows is not None:
        with _TABLE_CACHE_LOCK:
            _TABLE_CACHE[key] = table.copy()
            while len(_TABLE_CACHE) > _TABLE_CACHE_SIZE:
                _TABLE_CACHE.popitem(last=False)
    return table
