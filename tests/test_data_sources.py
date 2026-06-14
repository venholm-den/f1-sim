from __future__ import annotations

import pandas as pd

from src.data_sources.fia_documents import build_fia_context, ensure_fia_document_index
from src.data_sources.openf1 import build_live_timing_table
from src.data_sources.roadmap import build_data_source_roadmap, describe_openf1_endpoints


def test_data_source_roadmap_contains_openf1_and_fia() -> None:
    roadmap = build_data_source_roadmap()

    assert not roadmap.empty
    assert {"OpenF1", "FIA documents"}.issubset(set(roadmap["source"]))


def test_openf1_endpoint_description_contains_expected_endpoints() -> None:
    endpoints = describe_openf1_endpoints()

    expected = {"position", "intervals", "pit", "stints", "race_control"}
    assert expected.issubset(set(endpoints["endpoint"]))


def test_build_live_timing_table_combines_latest_rows() -> None:
    snapshot = {
        "drivers": pd.DataFrame(
            {
                "driver_number": [63, 44],
                "name_acronym": ["RUS", "HAM"],
                "team_name": ["Mercedes", "Ferrari"],
            }
        ),
        "position": pd.DataFrame(
            {
                "driver_number": [63, 63, 44],
                "date": [
                    "2026-01-01T00:00:01",
                    "2026-01-01T00:00:05",
                    "2026-01-01T00:00:05",
                ],
                "position": [2, 1, 2],
            }
        ),
        "intervals": pd.DataFrame(
            {
                "driver_number": [63, 44],
                "date": ["2026-01-01T00:00:05", "2026-01-01T00:00:05"],
                "gap_to_leader": [0.0, 1.2],
                "interval": [0.0, 1.2],
            }
        ),
        "stints": pd.DataFrame(
            {
                "driver_number": [63, 44],
                "date": ["2026-01-01T00:00:05", "2026-01-01T00:00:05"],
                "compound": ["MEDIUM", "SOFT"],
                "stint_number": [1, 1],
            }
        ),
        "pit": pd.DataFrame(),
        "race_control": pd.DataFrame(),
    }

    table = build_live_timing_table(snapshot)

    assert len(table) == 2
    assert list(table.sort_values("position")["name_acronym"]) == ["RUS", "HAM"]
    assert "gap_to_leader" in table.columns
    assert "compound" in table.columns


def test_fia_document_index_can_be_created(tmp_path) -> None:
    path = tmp_path / "fia_document_index.csv"

    created = ensure_fia_document_index(str(path))

    assert created == str(path)
    assert path.exists()

    context = build_fia_context(path=str(path))

    assert set(context) == {"official_grid", "penalties", "summons", "classification"}