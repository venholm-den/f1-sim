from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


DATA_SOURCE_REQUIREMENTS = {
    "fantasy_prices": {
        "path_key": "fantasy_prices_path",
        "label": "Fantasy Prices",
        "required_columns": ["Driver"],
    },
    "track_profiles": {
        "path_key": "track_profiles_path",
        "label": "Track Profiles",
        "required_columns": ["Event", "OvertakingDifficulty"],
    },
    "fia_document_index": {
        "path_key": "fia_document_index_path",
        "label": "FIA Document Index",
        "required_columns": ["year", "event", "document_type"],
    },
    "team_power_units": {
        "path_key": "team_power_units_path",
        "label": "Team Power Units",
        "required_columns": ["Year", "Team", "PowerUnitSupplier"],
    },
}


@dataclass(frozen=True)
class DataSourceStatus:
    key: str
    label: str
    path: str
    exists: bool
    status: str
    row_count: int
    missing_columns: list[str]
    modified_at: str
    message: str


def _config_data_paths(config: dict[str, Any]) -> dict[str, str]:
    data = config.get("data", {})

    return {
        key: str(data.get(requirement["path_key"], ""))
        for key, requirement in DATA_SOURCE_REQUIREMENTS.items()
    }


def validate_data_sources(config: dict[str, Any]) -> list[DataSourceStatus]:
    paths = _config_data_paths(config)
    statuses: list[DataSourceStatus] = []

    for key, path_text in paths.items():
        requirement = DATA_SOURCE_REQUIREMENTS[key]
        file_path = Path(path_text)

        if not path_text or not file_path.exists():
            statuses.append(
                DataSourceStatus(
                    key=key,
                    label=str(requirement["label"]),
                    path=path_text,
                    exists=False,
                    status="missing",
                    row_count=0,
                    missing_columns=list(requirement["required_columns"]),
                    modified_at="",
                    message="File is missing.",
                )
            )
            continue

        try:
            frame = pd.read_csv(file_path)
            required_columns = list(requirement["required_columns"])
            missing = [column for column in required_columns if column not in frame.columns]
            status = "valid" if not missing else "invalid"
            message = "Ready" if not missing else f"Missing columns: {', '.join(missing)}"
        except Exception as exc:
            frame = pd.DataFrame()
            missing = list(requirement["required_columns"])
            status = "invalid"
            message = f"Could not read CSV: {exc}"

        modified_at = ""

        try:
            modified_at = pd.Timestamp(file_path.stat().st_mtime, unit="s").strftime(
                "%Y-%m-%d %H:%M"
            )
        except Exception:
            pass

        statuses.append(
            DataSourceStatus(
                key=key,
                label=str(requirement["label"]),
                path=path_text,
                exists=True,
                status=status,
                row_count=len(frame),
                missing_columns=missing,
                modified_at=modified_at,
                message=message,
            )
        )

    return statuses


def read_csv_preview(path: str | Path, max_rows: int = 50) -> pd.DataFrame:
    file_path = Path(path)

    if not file_path.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(file_path, nrows=max_rows)
    except Exception:
        return pd.DataFrame()

