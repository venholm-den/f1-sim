from __future__ import annotations

from pathlib import Path

import pandas as pd


DEFAULT_TRACK_PROFILE = {
    "event": "Default",
    "overtaking_difficulty": 0.55,
    "safety_car_chance": 0.40,
    "red_flag_base_chance": 0.035,
    "notes": "Default profile",
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

    return {
        "event": str(row.get("Event", event_name)),
        "overtaking_difficulty": float(row.get("OvertakingDifficulty", 0.55)),
        "safety_car_chance": float(row.get("SafetyCarChance", 0.40)),
        "red_flag_base_chance": float(row.get("RedFlagBaseChance", 0.035)),
        "notes": str(row.get("Notes", "")),
    }