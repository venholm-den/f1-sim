from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


FIA_DOCUMENT_INDEX_PATH = "data/fia_documents/fia_document_index.csv"


FIA_DOCUMENT_COLUMNS = [
    "year",
    "event",
    "session",
    "document_type",
    "doc_number",
    "document_title",
    "document_url",
    "published_at",
    "driver",
    "team",
    "grid_position",
    "classification_position",
    "penalty_type",
    "penalty_value",
    "summons_reason",
    "status",
    "notes",
]


def ensure_fia_document_index(
    path: str = FIA_DOCUMENT_INDEX_PATH,
) -> str:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not output_path.exists():
        pd.DataFrame(columns=FIA_DOCUMENT_COLUMNS).to_csv(output_path, index=False)

    return str(output_path)


def load_fia_document_index(
    path: str = FIA_DOCUMENT_INDEX_PATH,
) -> pd.DataFrame:
    ensure_fia_document_index(path)

    df = pd.read_csv(path)

    for col in FIA_DOCUMENT_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    df["driver"] = df["driver"].astype(str).str.strip().str.upper()
    df["event"] = df["event"].astype(str).str.strip()
    df["document_type"] = df["document_type"].astype(str).str.strip().str.lower()

    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["grid_position"] = pd.to_numeric(df["grid_position"], errors="coerce")
    df["classification_position"] = pd.to_numeric(
        df["classification_position"],
        errors="coerce",
    )

    return df[FIA_DOCUMENT_COLUMNS].copy()


def _filter_event(
    df: pd.DataFrame,
    year: int | None = None,
    event: str | None = None,
    session: str | None = None,
) -> pd.DataFrame:
    output = df.copy()

    if year is not None and "year" in output.columns:
        output = output[output["year"].eq(year)]

    if event is not None and "event" in output.columns:
        event_lower = event.strip().lower()
        output = output[output["event"].astype(str).str.lower().eq(event_lower)]

    if session is not None and "session" in output.columns:
        session_lower = session.strip().lower()
        output = output[output["session"].astype(str).str.lower().eq(session_lower)]

    return output.reset_index(drop=True)


def official_grid(
    year: int | None = None,
    event: str | None = None,
    session: str | None = None,
    path: str = FIA_DOCUMENT_INDEX_PATH,
) -> pd.DataFrame:
    df = _filter_event(
        load_fia_document_index(path),
        year=year,
        event=event,
        session=session,
    )

    grid = df[
        df["document_type"].isin(
            [
                "grid",
                "starting grid",
                "official starting grid",
                "final starting grid",
            ]
        )
    ].copy()

    grid = grid.dropna(subset=["driver", "grid_position"])

    if grid.empty:
        return pd.DataFrame(columns=["Driver", "fia_grid_position", "fia_grid_source"])

    grid["Driver"] = grid["driver"].astype(str).str.upper()
    grid["fia_grid_position"] = grid["grid_position"].astype(int)
    grid["fia_grid_source"] = grid["document_title"].fillna("FIA official grid")

    return grid[
        [
            "Driver",
            "team",
            "fia_grid_position",
            "fia_grid_source",
            "document_url",
            "published_at",
        ]
    ].sort_values("fia_grid_position").reset_index(drop=True)


def penalties(
    year: int | None = None,
    event: str | None = None,
    session: str | None = None,
    path: str = FIA_DOCUMENT_INDEX_PATH,
) -> pd.DataFrame:
    df = _filter_event(
        load_fia_document_index(path),
        year=year,
        event=event,
        session=session,
    )

    output = df[
        df["document_type"].isin(
            [
                "penalty",
                "decision",
                "stewards decision",
                "grid penalty",
            ]
        )
        | df["penalty_type"].notna()
    ].copy()

    return output.reset_index(drop=True)


def summons(
    year: int | None = None,
    event: str | None = None,
    session: str | None = None,
    path: str = FIA_DOCUMENT_INDEX_PATH,
) -> pd.DataFrame:
    df = _filter_event(
        load_fia_document_index(path),
        year=year,
        event=event,
        session=session,
    )

    output = df[
        df["document_type"].isin(["summons", "summon"])
        | df["summons_reason"].notna()
    ].copy()

    return output.reset_index(drop=True)


def classification(
    year: int | None = None,
    event: str | None = None,
    session: str | None = None,
    path: str = FIA_DOCUMENT_INDEX_PATH,
) -> pd.DataFrame:
    df = _filter_event(
        load_fia_document_index(path),
        year=year,
        event=event,
        session=session,
    )

    output = df[
        df["document_type"].isin(
            [
                "classification",
                "final classification",
                "race classification",
                "qualifying classification",
            ]
        )
        | df["classification_position"].notna()
    ].copy()

    if output.empty:
        return output

    output["Driver"] = output["driver"].astype(str).str.upper()

    return output.reset_index(drop=True)


def build_fia_context(
    year: int | None = None,
    event: str | None = None,
    session: str | None = None,
    path: str = FIA_DOCUMENT_INDEX_PATH,
) -> dict[str, pd.DataFrame]:
    """
    Returns official FIA context frames for future integration.

    Intended consumers:
    - grid.py: official starting grids and penalties
    - strategy.py: summons/penalties that affect tyre/race assumptions
    - report_card.py: show FIA notes and official document links
    """

    return {
        "official_grid": official_grid(year=year, event=event, session=session, path=path),
        "penalties": penalties(year=year, event=event, session=session, path=path),
        "summons": summons(year=year, event=event, session=session, path=path),
        "classification": classification(year=year, event=event, session=session, path=path),
    }


def save_fia_context(
    context: dict[str, pd.DataFrame],
    output_dir: str = "outputs/data_sources/fia",
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    saved: dict[str, str] = {}

    for name, df in context.items():
        file_path = output_path / f"{name}.csv"
        df.to_csv(file_path, index=False)
        saved[name] = str(file_path)

    return saved


def create_example_fia_document_index(
    path: str = FIA_DOCUMENT_INDEX_PATH,
) -> str:
    """
    Creates a starter/example CSV if one does not already exist.
    """

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and output_path.stat().st_size > 0:
        return str(output_path)

    example = pd.DataFrame(
        [
            {
                "year": 2026,
                "event": "Barcelona Grand Prix",
                "session": "R",
                "document_type": "official starting grid",
                "doc_number": "Doc XX",
                "document_title": "Official Starting Grid",
                "document_url": "",
                "published_at": "",
                "driver": "RUS",
                "team": "Mercedes",
                "grid_position": 1,
                "classification_position": pd.NA,
                "penalty_type": "",
                "penalty_value": "",
                "summons_reason": "",
                "status": "",
                "notes": "Example row. Replace with real FIA scraper output.",
            }
        ],
        columns=FIA_DOCUMENT_COLUMNS,
    )

    example.to_csv(output_path, index=False)

    return str(output_path)