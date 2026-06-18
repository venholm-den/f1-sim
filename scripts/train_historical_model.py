from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.historical_model import train_historical_models


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train historical sklearn calibration models.")
    parser.add_argument("--historical-dir", default="data/historical_model")
    parser.add_argument("--model-dir", default="data/models")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = train_historical_models(
        historical_dir=args.historical_dir,
        model_dir=args.model_dir,
    )
    metrics = json.loads(Path(artifacts.metrics).read_text(encoding="utf-8"))

    print("Historical model training complete.")
    print(f"feature_table: {artifacts.feature_table}")
    print(f"finish_model: {artifacts.finish_model}")
    print(f"dnf_model: {artifacts.dnf_model}")
    print(f"metrics: {artifacts.metrics}")
    print(f"finish_mae: {metrics.get('finish_mae'):.3f}")
    print(f"finish_rmse: {metrics.get('finish_rmse'):.3f}")
    print(f"dnf_brier: {metrics.get('dnf_brier'):.3f}")


if __name__ == "__main__":
    main()
