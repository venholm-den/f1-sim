"""Record independent OpenF1 classification/tyre checks without posting."""
import argparse
import json
from pathlib import Path

from portable_app.instance_lock import workspace_lock
from src.app_services.classification_checks import capture_checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--forecast-folder', type=Path, required=True)
    parser.add_argument('--official-folder', type=Path)
    args = parser.parse_args()
    root = args.workspace.resolve()
    with workspace_lock(root):
        result = capture_checks(root, root/args.forecast_folder,
                                official_folder=root/args.official_folder if args.official_folder else None)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
