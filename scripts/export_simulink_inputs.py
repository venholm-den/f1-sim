"""Export Python model outputs to the Simulink lap-dynamics CSV contract."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.simulink_export import export_simulink_inputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--features",
        default="outputs/driver_model_features.csv",
        help="Driver model feature CSV produced by main.py.",
    )
    parser.add_argument(
        "--strategies",
        default="outputs/strategy/predicted_tyre_strategy.csv",
        help="Optional strategy CSV used to derive the number of pit stops.",
    )
    parser.add_argument(
        "--output",
        default="outputs/matlab/lap_dynamics_inputs.csv",
        help="Destination CSV consumed by matlab/run_lap_dynamics.m.",
    )
    parser.add_argument("--initial-fuel-penalty", type=float, default=3.0)
    parser.add_argument("--fuel-gain-per-lap", type=float, default=0.05)
    parser.add_argument("--pit-loss", type=float, default=22.0)
    parser.add_argument("--max-tyre-degradation", type=float, default=0.25)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = export_simulink_inputs(
        features_path=args.features,
        strategies_path=args.strategies,
        output_path=args.output,
        initial_fuel_penalty_seconds=args.initial_fuel_penalty,
        fuel_gain_per_lap_seconds=args.fuel_gain_per_lap,
        pit_loss_seconds=args.pit_loss,
        max_tyre_degradation_seconds_per_lap=args.max_tyre_degradation,
    )
    print(f"Wrote Simulink input contract to {output_path}")


if __name__ == "__main__":
    main()
