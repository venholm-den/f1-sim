from __future__ import annotations

from src.track import ensure_track_profiles_file, load_track_profile


def test_generated_track_profiles_include_forecast_coordinates(tmp_path) -> None:
    path = tmp_path / "track_profiles.csv"

    ensure_track_profiles_file(str(path))
    profile = load_track_profile("Barcelona Grand Prix", path=str(path))

    assert profile["event"] == "Barcelona Grand Prix"
    assert profile["latitude"] == 41.57
    assert profile["longitude"] == 2.2611
