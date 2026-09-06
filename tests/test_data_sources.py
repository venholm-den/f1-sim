from __future__ import annotations

import pandas as pd

from src.data_sources.fia_documents import (
    FiaDocumentListing,
    build_fia_context,
    ensure_fia_document_index,
    merge_fia_document_rows,
    parse_fia_competitor_rows_from_text,
    parse_fia_document_listing_html,
    parse_fia_event_urls,
    parse_fia_stewards_row_from_title,
)
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

def test_blank_fia_fields_do_not_create_false_penalties_or_summons(tmp_path) -> None:
    path = tmp_path / "fia_document_index.csv"

    pd.DataFrame(
        [
            {
                "year": 2026,
                "event": "Barcelona Grand Prix",
                "session": "R",
                "document_type": "official starting grid",
                "doc_number": "Doc 01",
                "document_title": "Official Starting Grid",
                "document_url": "",
                "published_at": "",
                "driver": "RUS",
                "team": "Mercedes",
                "grid_position": 1,
                "classification_position": "",
                "penalty_type": "",
                "penalty_value": "",
                "summons_reason": "",
                "status": "",
                "notes": "",
            }
        ]
    ).to_csv(path, index=False)

    context = build_fia_context(
        year=2026,
        event="Barcelona Grand Prix",
        session="R",
        path=str(path),
    )

    assert len(context["official_grid"]) == 1
    assert context["penalties"].empty
    assert context["summons"].empty
    assert context["classification"].empty


def test_fia_document_listing_html_is_parsed() -> None:
    html = """
    <div class="event-title active">Hungarian Grand Prix</div>
    <li class="document-row key-46">
      <a href="/system/files/decision-document/grid.pdf">
        <div class="title">Doc 46 - Provisional Starting Grid</div>
        <div class="published">
          Published on <span class="date-display-single">25.07.26 20:00</span> CET
        </div>
      </a>
    </li>
    <li class="document-row key-45">
      <a href="/system/files/decision-document/quali.pdf">
        <div class="title">Doc 45 - Final Qualifying Classification</div>
        <div class="published">Published on 25.07.26 19:30 CET</div>
      </a>
    </li>
    """

    listings = parse_fia_document_listing_html(
        html,
        year=2026,
        base_url="https://www.fia.com/documents/example",
    )

    assert len(listings) == 2
    assert listings[0].event == "Hungarian Grand Prix"
    assert listings[0].doc_number == "Doc 46"
    assert listings[0].document_type == "starting grid"
    assert listings[0].session == "R"
    assert listings[0].document_url == "https://www.fia.com/system/files/decision-document/grid.pdf"
    assert listings[1].document_type == "qualifying classification"
    assert listings[1].session == "Q"


def test_fia_event_filter_urls_are_parsed() -> None:
    html = """
    <select>
      <option value="0">Event</option>
      <option value="/documents/championships/fia-formula-one-world-championship-14/season/season-2026-2072/event/Hungarian%20Grand%20Prix">Hungarian Grand Prix</option>
      <option value="/documents/championships/fia-formula-one-world-championship-14/season/season-2026-2072/event/British%20Grand%20Prix">British Grand Prix</option>
    </select>
    """

    urls = parse_fia_event_urls(html, base_url="https://www.fia.com/documents/example")

    assert urls == [
        "https://www.fia.com/documents/championships/fia-formula-one-world-championship-14/season/season-2026-2072/event/Hungarian%20Grand%20Prix",
        "https://www.fia.com/documents/championships/fia-formula-one-world-championship-14/season/season-2026-2072/event/British%20Grand%20Prix",
    ]


def test_fia_competitor_text_uses_driver_map() -> None:
    listing = FiaDocumentListing(
        year=2026,
        event="Hungarian Grand Prix",
        document_type="starting grid",
        doc_number="Doc 46",
        document_title="Provisional Starting Grid",
        document_url="https://example.test/grid.pdf",
        published_at="25.07.26 20:00 CET",
        session="R",
    )
    text = """
    Pos No Driver Team
    1 81 Oscar Piastri McLaren Mercedes
    2 63 George Russell Mercedes
    """

    rows = parse_fia_competitor_rows_from_text(
        text,
        listing,
        driver_map={
            "81": {"driver": "PIA", "team": "McLaren"},
            "63": {"driver": "RUS", "team": "Mercedes"},
        },
    )

    assert [row["driver"] for row in rows] == ["PIA", "RUS"]
    assert [row["grid_position"] for row in rows] == [1, 2]


def test_fia_stewards_title_row_uses_reason_fields() -> None:
    listing = FiaDocumentListing(
        year=2026,
        event="Hungarian Grand Prix",
        document_type="summons",
        doc_number="Doc 16",
        document_title="Summons - Car 55 - Alleged erratic driving in turn 9",
        document_url="https://example.test/summons.pdf",
        published_at="25.07.26 12:00 CET",
        session="",
    )

    row = parse_fia_stewards_row_from_title(
        listing,
        driver_map={"55": {"driver": "SAI", "team": "Williams"}},
    )

    assert row is not None
    assert row["driver"] == "SAI"
    assert row["summons_reason"] == "Alleged erratic driving in turn 9"


def test_fia_document_merge_deduplicates_on_document_and_driver() -> None:
    existing = pd.DataFrame(
        [
            {
                "year": 2026,
                "event": "Hungarian Grand Prix",
                "session": "R",
                "document_type": "starting grid",
                "doc_number": "Doc 46",
                "document_title": "Provisional Starting Grid",
                "document_url": "https://example.test/grid.pdf",
                "published_at": "old",
                "driver": "",
                "team": "",
                "grid_position": "",
                "classification_position": "",
                "penalty_type": "",
                "penalty_value": "",
                "summons_reason": "",
                "status": "metadata",
                "notes": "",
            }
        ]
    )

    merged = merge_fia_document_rows(
        existing,
        [
            {
                "year": 2026,
                "event": "Hungarian Grand Prix",
                "session": "R",
                "document_type": "starting grid",
                "doc_number": "Doc 46",
                "document_title": "Provisional Starting Grid",
                "document_url": "https://example.test/grid.pdf",
                "published_at": "new",
                "driver": "",
                "team": "",
                "grid_position": "",
                "classification_position": "",
                "penalty_type": "",
                "penalty_value": "",
                "summons_reason": "",
                "status": "metadata",
                "notes": "",
            }
        ],
    )

    assert len(merged) == 1
    assert merged.loc[0, "published_at"] == "new"
