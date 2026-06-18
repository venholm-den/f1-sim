from __future__ import annotations

import pandas as pd

from src.historical_data import HistoricalBuildConfig, build_historical_dataset


class FakeSession:
    def __init__(self) -> None:
        self.laps = pd.DataFrame(
            {
                "Driver": ["AAA", "AAA"],
                "DriverNumber": ["1", "1"],
                "Team": ["Test Team", "Test Team"],
                "LapNumber": [1, 2],
                "Stint": [1, 1],
                "Compound": ["MEDIUM", "MEDIUM"],
                "TyreLife": [1, 2],
                "FreshTyre": [True, True],
                "LapTime": [pd.Timedelta(seconds=90), pd.Timedelta(seconds=89)],
                "Sector1Time": [pd.Timedelta(seconds=30), pd.Timedelta(seconds=29)],
                "Sector2Time": [pd.Timedelta(seconds=31), pd.Timedelta(seconds=30)],
                "Sector3Time": [pd.Timedelta(seconds=29), pd.Timedelta(seconds=30)],
                "SpeedI1": [250, 252],
                "SpeedI2": [260, 262],
                "SpeedFL": [270, 272],
                "SpeedST": [300, 302],
                "IsPersonalBest": [False, True],
                "IsAccurate": [True, True],
                "TrackStatus": ["1", "1"],
                "Deleted": [False, False],
                "PitOutTime": [pd.NaT, pd.NaT],
                "PitInTime": [pd.NaT, pd.NaT],
                "LapStartTime": [pd.Timedelta(seconds=0), pd.Timedelta(seconds=90)],
            }
        )
        self.results = pd.DataFrame(
            {
                "DriverNumber": ["1"],
                "Abbreviation": ["AAA"],
                "TeamName": ["Test Team"],
                "Position": [1],
                "ClassifiedPosition": ["1"],
                "Status": ["Finished"],
                "Points": [25],
                "GridPosition": [1],
            }
        )
        self.weather_data = pd.DataFrame(
            {
                "AirTemp": [21.0],
                "TrackTemp": [32.0],
                "Humidity": [50.0],
                "Pressure": [1010.0],
                "WindSpeed": [2.0],
                "Rainfall": [False],
            }
        )

    def load(self, **kwargs) -> None:
        return None


def test_build_historical_dataset_writes_normalized_outputs(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "src.historical_data._event_candidates",
        lambda *args, **kwargs: [{"year": 2026, "round": 1, "event": "Test Grand Prix"}],
    )
    monkeypatch.setattr(
        "src.historical_data.load_session",
        lambda year, event, session: (
            FakeSession(),
            {"year": year, "event": "Test Grand Prix", "round": event, "session": session},
        ),
    )

    outputs = build_historical_dataset(
        HistoricalBuildConfig(
            start_year=2026,
            end_year=2026,
            output_dir=str(tmp_path),
            sessions=("R",),
            include_openf1=False,
        )
    )

    laps = pd.read_csv(outputs["laps"])
    results = pd.read_csv(outputs["race_results"])
    manifest = pd.read_csv(outputs["manifest"])

    assert laps.loc[0, "Year"] == 2026
    assert laps.loc[0, "Event"] == "Test Grand Prix"
    assert results.loc[0, "Status"] == "Finished"
    assert manifest.loc[0, "status"] == "ok"


def test_build_historical_dataset_stops_on_rate_limit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "src.historical_data._event_candidates",
        lambda *args, **kwargs: [
            {"year": 2026, "round": 1, "event": "One Grand Prix"},
            {"year": 2026, "round": 2, "event": "Two Grand Prix"},
        ],
    )

    calls = []

    def fake_load_session(year, event, session):
        calls.append((year, event, session))
        raise RuntimeError("any API: 500 calls/h")

    monkeypatch.setattr("src.historical_data.load_session", fake_load_session)

    outputs = build_historical_dataset(
        HistoricalBuildConfig(
            start_year=2026,
            end_year=2026,
            output_dir=str(tmp_path),
            sessions=("R",),
            include_openf1=False,
        )
    )

    manifest = pd.read_csv(outputs["manifest"])

    assert len(calls) == 1
    assert manifest.loc[0, "status"] == "rate_limited"


def test_no_skip_existing_preserves_manifest_rows(tmp_path, monkeypatch) -> None:
    events = [{"year": 2026, "round": 1, "event": "One Grand Prix"}]
    monkeypatch.setattr("src.historical_data._event_candidates", lambda *args, **kwargs: events)
    monkeypatch.setattr(
        "src.historical_data.load_session",
        lambda year, event, session: (
            FakeSession(),
            {"year": year, "event": "One Grand Prix", "round": event, "session": session},
        ),
    )

    build_historical_dataset(
        HistoricalBuildConfig(
            start_year=2026,
            end_year=2026,
            output_dir=str(tmp_path),
            sessions=("R",),
            include_openf1=False,
        )
    )

    events[:] = [{"year": 2026, "round": 2, "event": "Two Grand Prix"}]
    outputs = build_historical_dataset(
        HistoricalBuildConfig(
            start_year=2026,
            end_year=2026,
            output_dir=str(tmp_path),
            sessions=("R",),
            include_openf1=False,
            skip_existing=False,
        )
    )

    manifest = pd.read_csv(outputs["manifest"])

    assert set(manifest["event"]) == {"One Grand Prix", "Two Grand Prix"}
