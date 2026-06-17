from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


MODEL_FEATURES_FILE = "driver_model_features.csv"
MODEL_COMMENTARY_FILE = "report/model_commentary.txt"

DISPLAY_COLUMNS = [
    "Driver",
    "Team",
    "grid_position",
    "grid_source",
    "current_signal_quality",
    "effective_current_weight",
    "model_uncertainty",
    "performance_uncertainty",
    "quali_pace_score",
    "race_pace_score",
    "strategy_score",
    "reliability_score",
    "engine_reliability_score",
    "projected_lap_time",
]


@dataclass(frozen=True)
class ModelSignals:
    output_dir: str
    features_path: str
    commentary_path: str
    features_exist: bool
    overview: pd.DataFrame
    driver_signals: pd.DataFrame
    commentary: str


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _mean(frame: pd.DataFrame, column: str) -> str:
    if column not in frame.columns or frame.empty:
        return "n/a"

    values = pd.to_numeric(frame[column], errors="coerce").dropna()

    if values.empty:
        return "n/a"

    return f"{float(values.mean()):.3f}"


def _count_matching(frame: pd.DataFrame, column: str, value: str) -> int:
    if column not in frame.columns:
        return 0

    return int(frame[column].astype(str).str.casefold().eq(value.casefold()).sum())


def _build_overview(frame: pd.DataFrame, features_path: Path) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            [
                {
                    "Metric": "Driver model features",
                    "Value": "missing",
                    "Note": str(features_path),
                }
            ]
        )

    outliers = 0
    if "current_pace_outlier_flag" in frame.columns:
        outliers = int(
            frame["current_pace_outlier_flag"].astype(str).str.lower().isin(["true", "1"]).sum()
        )

    rows = [
        {"Metric": "Drivers", "Value": str(len(frame)), "Note": "Rows in model feature file"},
        {
            "Metric": "Avg current signal quality",
            "Value": _mean(frame, "current_signal_quality"),
            "Note": "Higher means current session data is cleaner and more trusted",
        },
        {
            "Metric": "Avg current-session weight",
            "Value": _mean(frame, "effective_current_weight"),
            "Note": "How much the model blended current-session pace over baseline pace",
        },
        {
            "Metric": "Avg model uncertainty",
            "Value": _mean(frame, "model_uncertainty"),
            "Note": "Higher means less confidence in the raw driver model",
        },
        {
            "Metric": "Avg performance uncertainty",
            "Value": _mean(frame, "performance_uncertainty"),
            "Note": "Higher means more spread in final projected performance",
        },
        {
            "Metric": "Current pace outliers",
            "Value": str(outliers),
            "Note": "Drivers whose current-session pace was treated cautiously",
        },
        {
            "Metric": "Actual grid rows",
            "Value": str(_count_matching(frame, "grid_source", "actual_session_results")),
            "Note": "Grid positions read from session classification/results",
        },
        {
            "Metric": "FIA grid rows",
            "Value": str(_count_matching(frame, "grid_source", "fia_document_index")),
            "Note": "Grid positions read from the FIA document index",
        },
    ]

    return pd.DataFrame(rows)


def _driver_signal_view(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    output = frame[[column for column in DISPLAY_COLUMNS if column in frame.columns]].copy()

    if "grid_position" in output.columns:
        output["_sort_grid"] = pd.to_numeric(output["grid_position"], errors="coerce")
        output = output.sort_values(["_sort_grid", "Driver"], na_position="last")
        output = output.drop(columns=["_sort_grid"])
    elif "model_pace" in frame.columns:
        output["_sort_pace"] = pd.to_numeric(frame["model_pace"], errors="coerce")
        output = output.sort_values(["_sort_pace", "Driver"], na_position="last")
        output = output.drop(columns=["_sort_pace"])

    numeric_columns = [
        "current_signal_quality",
        "effective_current_weight",
        "model_uncertainty",
        "performance_uncertainty",
        "quali_pace_score",
        "race_pace_score",
        "strategy_score",
        "reliability_score",
        "engine_reliability_score",
        "projected_lap_time",
    ]

    for column in numeric_columns:
        if column in output.columns:
            output[column] = pd.to_numeric(output[column], errors="coerce").map(
                lambda value: "" if pd.isna(value) else f"{float(value):.3f}"
            )

    return output


def load_model_signals(output_dir: str | Path) -> ModelSignals:
    root = Path(output_dir)
    features_path = root / MODEL_FEATURES_FILE
    commentary_path = root / MODEL_COMMENTARY_FILE
    frame = _read_csv(features_path)
    commentary = ""

    if commentary_path.exists():
        try:
            commentary = commentary_path.read_text(encoding="utf-8").strip()
        except Exception:
            commentary = ""

    return ModelSignals(
        output_dir=str(root),
        features_path=str(features_path),
        commentary_path=str(commentary_path),
        features_exist=features_path.exists(),
        overview=_build_overview(frame, features_path),
        driver_signals=_driver_signal_view(frame),
        commentary=commentary,
    )
