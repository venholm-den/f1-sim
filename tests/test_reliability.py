from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from src.reliability import (
    apply_reliability_profile,
    classify_result_status,
    infer_reliability_profile,
    load_team_power_units,
)


def test_classify_result_status_separates_mechanical_from_crash() -> None:
    assert classify_result_status("Engine") == "mechanical_dnf"
    assert classify_result_status("Gearbox") == "mechanical_dnf"
    assert classify_result_status("Accident") == "non_mechanical_dnf"
    assert classify_result_status("+1 Lap") == "finished"
    assert classify_result_status("Retired") == "unknown"


def test_infer_reliability_profile_from_recent_race_results() -> None:
    session = SimpleNamespace(
        results=pd.DataFrame(
            {
                "Abbreviation": ["RUS", "HAM", "LEC", "BEA"],
                "TeamName": ["Mercedes", "Mercedes", "Ferrari", "Haas F1 Team"],
                "Status": ["Engine", "Finished", "Finished", "Accident"],
            }
        )
    )
    mapping = pd.DataFrame(
        {
            "Year": [2026, 2026, 2026],
            "Team": ["Mercedes", "Ferrari", "Haas F1 Team"],
            "PowerUnitSupplier": ["Mercedes", "Ferrari", "Ferrari"],
            "team_key": ["mercedes", "ferrari", "haas f1 team"],
        }
    )

    profile = infer_reliability_profile(
        recent_races=[(session, {"year": 2026, "event": "Test Grand Prix"})],
        team_power_units=mapping,
    )

    rows = profile.set_index("Team")

    assert rows.loc["Mercedes", "PowerUnitSupplier"] == "Mercedes"
    assert rows.loc["Mercedes", "team_mechanical_dnf_rate"] > rows.loc["Ferrari", "team_mechanical_dnf_rate"]
    assert rows.loc["Ferrari", "PowerUnitSupplier"] == "Ferrari"
    assert rows.loc["Haas F1 Team", "PowerUnitSupplier"] == "Ferrari"
    assert rows.loc["Mercedes", "reliability_profile_source"] == "recent_race_result_status_inference"


def test_apply_reliability_profile_blends_team_and_power_unit_rates() -> None:
    model_features = pd.DataFrame(
        {
            "Driver": ["RUS", "LEC"],
            "Team": ["Mercedes", "Ferrari"],
            "dnf_prob": [0.04, 0.04],
        }
    )
    profile = pd.DataFrame(
        {
            "team_key": ["mercedes", "ferrari"],
            "PowerUnitSupplier": ["Mercedes", "Ferrari"],
            "team_mechanical_dnf_rate": [0.12, 0.02],
            "power_unit_mechanical_dnf_rate": [0.10, 0.03],
            "engine_reliability_score": [0.90, 0.97],
            "reliability_profile_source": ["test", "test"],
        }
    )

    output = apply_reliability_profile(model_features, profile)
    rows = output.set_index("Driver")

    assert rows.loc["RUS", "base_dnf_prob"] == 0.04
    assert rows.loc["RUS", "dnf_prob"] > rows.loc["LEC", "dnf_prob"]
    assert rows.loc["RUS", "PowerUnitSupplier"] == "Mercedes"
    assert rows.loc["LEC", "engine_reliability_score"] == 0.97


def test_load_team_power_units_validates_required_columns(tmp_path) -> None:
    path = tmp_path / "team_power_units.csv"
    pd.DataFrame({"Team": ["Mercedes"]}).to_csv(path, index=False)

    try:
        load_team_power_units(path)
    except ValueError as exc:
        assert "PowerUnitSupplier" in str(exc)
    else:
        raise AssertionError("Expected invalid mapping to raise ValueError")
