from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.historical_model import train_historical_models


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train historical sklearn calibration models.")
    parser.add_argument("--historical-dir", default="data/historical_model")
    parser.add_argument("--model-dir", default=None, help='New candidate directory; existing artifacts are never overwritten.')
    parser.add_argument('--finish-target', choices=['absolute', 'grid_residual'], default='grid_residual')
    parser.add_argument('--enriched', action='store_true', help='Experimental pre-Q practice and prior-round reliability features.')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = train_historical_models(
        historical_dir=args.historical_dir,
        model_dir=args.model_dir or Path('outputs/model_candidates')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'),
        finish_target=args.finish_target,
        enriched=args.enriched,
    )
    metrics = json.loads(Path(artifacts.metrics).read_text(encoding="utf-8"))

    print("Historical model training complete.")
    print(f"feature_table: {artifacts.feature_table}")
    print(f"finish_model: {artifacts.finish_model}")
    print(f"dnf_model: {artifacts.dnf_model}")
    print(f"metrics: {artifacts.metrics}")
    print(f"finish_mae: {metrics.get('finish_mae'):.3f}")
    print(f"finish_rmse: {metrics.get('finish_rmse'):.3f}")
    brier = metrics.get('dnf_brier')
    print('dnf_brier: ' + ('unavailable' if brier is None else f'{brier:.3f}'))
    print('Candidate only; inactive pending independent validation.')


if __name__ == "__main__":
    main()
