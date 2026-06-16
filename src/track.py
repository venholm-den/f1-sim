from __future__ import annotations

from pathlib import Path

import pandas as pd


DEFAULT_TRACK_PROFILE = {
    "event": "Default",
    "overtaking_difficulty": 0.55,
    "safety_car_chance": 0.40,
    "red_flag_base_chance": 0.035,
    "latitude": None,
    "longitude": None,
    "notes": "Default profile",
}


TRACK_COORDINATES = {
    "Bahrain Grand Prix": (26.0325, 50.5106),
    "Saudi Arabian Grand Prix": (21.6319, 39.1044),
    "Australian Grand Prix": (-37.8497, 144.9680),
    "Monaco Grand Prix": (43.7347, 7.4206),
    "Barcelona Grand Prix": (41.5700, 2.2611),
    "Spanish Grand Prix": (41.5700, 2.2611),
    "Canadian Grand Prix": (45.5000, -73.5228),
    "British Grand Prix": (52.0733, -1.0147),
    "Hungarian Grand Prix": (47.5830, 19.2526),
    "Dutch Grand Prix": (52.3888, 4.5409),
    "Italian Grand Prix": (45.6218, 9.2895),
    "Singapore Grand Prix": (1.2914, 103.8640),
    "Abu Dhabi Grand Prix": (24.4672, 54.6031),
}


def ensure_track_profiles_file(path: str = "data/track_profiles.csv") -> None:
    file_path = Path(path)

    if file_path.exists():
        return

    file_path.parent.mkdir(parents=True, exist_ok=True)

    starter = pd.DataFrame(
        [
            {
                "Event": "Bahrain Grand Prix",
                "OvertakingDifficulty": 0.45,
                "SafetyCarChance": 0.35,
                "RedFlagBaseChance": 0.030,
                "Notes": "Good overtaking",
            },
            {
                "Event": "Saudi Arabian Grand Prix",
                "OvertakingDifficulty": 0.50,
                "SafetyCarChance": 0.55,
                "RedFlagBaseChance": 0.060,
                "Notes": "Fast street circuit",
            },
            {
                "Event": "Australian Grand Prix",
                "OvertakingDifficulty": 0.55,
                "SafetyCarChance": 0.50,
                "RedFlagBaseChance": 0.050,
                "Notes": "Moderate overtaking",
            },
            {
                "Event": "Monaco Grand Prix",
                "OvertakingDifficulty": 0.88,
                "SafetyCarChance": 0.55,
                "RedFlagBaseChance": 0.080,
                "Notes": "Very hard to overtake",
            },
            {
                "Event": "Barcelona Grand Prix",
                "OvertakingDifficulty": 0.72,
                "SafetyCarChance": 0.35,
                "RedFlagBaseChance": 0.035,
                "Notes": "Barcelona: high tyre degradation and moderate-to-hard overtaking; grid position matters.",
            },
            {
                "Event": "Spanish Grand Prix",
                "OvertakingDifficulty": 0.72,
                "SafetyCarChance": 0.35,
                "RedFlagBaseChance": 0.035,
                "Notes": "Barcelona: high tyre degradation and moderate-to-hard overtaking; grid position matters.",
            },
            {
                "Event": "Canadian Grand Prix",
                "OvertakingDifficulty": 0.48,
                "SafetyCarChance": 0.55,
                "RedFlagBaseChance": 0.050,
                "Notes": "Good overtaking and safety car risk",
            },
            {
                "Event": "British Grand Prix",
                "OvertakingDifficulty": 0.45,
                "SafetyCarChance": 0.40,
                "RedFlagBaseChance": 0.040,
                "Notes": "Good overtaking",
            },
            {
                "Event": "Hungarian Grand Prix",
                "OvertakingDifficulty": 0.72,
                "SafetyCarChance": 0.40,
                "RedFlagBaseChance": 0.040,
                "Notes": "Hard to overtake",
            },
            {
                "Event": "Dutch Grand Prix",
                "OvertakingDifficulty": 0.68,
                "SafetyCarChance": 0.45,
                "RedFlagBaseChance": 0.040,
                "Notes": "Track position important",
            },
            {
                "Event": "Italian Grand Prix",
                "OvertakingDifficulty": 0.38,
                "SafetyCarChance": 0.35,
                "RedFlagBaseChance": 0.030,
                "Notes": "Low drag, easier overtaking",
            },
            {
                "Event": "Singapore Grand Prix",
                "OvertakingDifficulty": 0.78,
                "SafetyCarChance": 0.65,
                "RedFlagBaseChance": 0.070,
                "Notes": "Street circuit chaos",
            },
            {
                "Event": "Abu Dhabi Grand Prix",
                "OvertakingDifficulty": 0.52,
                "SafetyCarChance": 0.35,
                "RedFlagBaseChance": 0.030,
                "Notes": "Moderate overtaking",
            },
        ]
    )

    starter["Latitude"] = starter["Event"].map(
        lambda event: TRACK_COORDINATES.get(str(event), (None, None))[0]
    )
    starter["Longitude"] = starter["Event"].map(
        lambda event: TRACK_COORDINATES.get(str(event), (None, None))[1]
    )

    starter.to_csv(file_path, index=False)


def load_track_profile(event_name: str, path: str = "data/track_profiles.csv") -> dict:
    ensure_track_profiles_file(path)

    profiles = pd.read_csv(path)
    profiles["Event"] = profiles["Event"].astype(str)

    event_name_clean = str(event_name).strip().lower()

    exact_match = profiles[
        profiles["Event"].str.strip().str.lower() == event_name_clean
    ]

    if exact_match.empty:
        partial_match = profiles[
            profiles["Event"].str.lower().apply(
                lambda value: value in event_name_clean or event_name_clean in value
            )
        ]
    else:
        partial_match = exact_match

    if partial_match.empty:
        return DEFAULT_TRACK_PROFILE.copy()

    row = partial_match.iloc[0]
    latitude = row.get("Latitude", row.get("latitude"))
    longitude = row.get("Longitude", row.get("longitude"))

    latitude = None if pd.isna(latitude) else latitude
    longitude = None if pd.isna(longitude) else longitude

    return {
        "event": str(row.get("Event", event_name)),
        "overtaking_difficulty": float(row.get("OvertakingDifficulty", 0.55)),
        "safety_car_chance": float(row.get("SafetyCarChance", 0.40)),
        "red_flag_base_chance": float(row.get("RedFlagBaseChance", 0.035)),
        "latitude": None if latitude is None else float(latitude),
        "longitude": None if longitude is None else float(longitude),
        "notes": str(row.get("Notes", "")),
    }
