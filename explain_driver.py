from pathlib import Path

import pandas as pd


DRIVER = "ANT"

Path("outputs/debug").mkdir(parents=True, exist_ok=True)

summary = pd.read_csv("outputs/simulation_summary.csv")
features = pd.read_csv("outputs/driver_model_features.csv")

summary_row = summary[summary["Driver"].astype(str) == DRIVER]
features_row = features[features["Driver"].astype(str) == DRIVER]

print()
print(f"=== {DRIVER} simulation summary ===")
print(summary_row.to_string(index=False))

print()
print(f"=== {DRIVER} model features ===")
print(features_row.to_string(index=False))

debug = summary.merge(
    features,
    on=["Driver", "Team"],
    how="left",
    suffixes=("", "_feature"),
)

debug.to_csv("outputs/debug/full_model_debug.csv", index=False)

print()
print("Saved:")
print("- outputs/debug/full_model_debug.csv")