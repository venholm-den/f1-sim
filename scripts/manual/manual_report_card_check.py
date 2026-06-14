from pathlib import Path

import pandas as pd

from src.report_card import build_report_outputs
from src.track import load_track_profile


Path("outputs/report").mkdir(parents=True, exist_ok=True)

summary = pd.read_csv("outputs/simulation_summary.csv")

if Path("outputs/weather_summary.csv").exists():
    weather_summary = pd.read_csv("outputs/weather_summary.csv").iloc[0].to_dict()
else:
    weather_summary = {}

metadata = {
    "year": 2026,
    "event": weather_summary.get("track_event", "Unknown Grand Prix"),
    "session": "Q",
}

track_profile = load_track_profile(str(metadata["event"]))

strategy_csv_path = "outputs/strategy/predicted_tyre_strategy.csv"

if not Path(strategy_csv_path).exists():
    strategy_csv_path = None

outputs = build_report_outputs(
    summary=summary,
    metadata=metadata,
    weather_summary=weather_summary,
    track_profile=track_profile,
    overtaking_difficulty=float(track_profile.get("overtaking_difficulty", 0.55)),
    strategy_csv_path=strategy_csv_path,
)

print("Generated report outputs:")

for name, path in outputs.items():
    print(f"- {name}: {Path(path).resolve()}")