from __future__ import annotations

import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


GENERATED_DIRECTORIES = [
    "outputs",
    "data/cache",
    "cache",
    ".fastf1",
    "fastf1_cache",
]

GENERATED_FILE_PATTERNS = [
    "outputs_lap_details_*.csv",
    "*.tmp",
]


def remove_directory(path: Path) -> None:
    if path.exists() and path.is_dir():
        shutil.rmtree(path)
        print(f"Removed directory: {path.relative_to(PROJECT_ROOT)}")


def remove_file(path: Path) -> None:
    if path.exists() and path.is_file():
        path.unlink()
        print(f"Removed file: {path.relative_to(PROJECT_ROOT)}")


def main() -> None:
    print("Cleaning generated local outputs...")
    print()

    for directory in GENERATED_DIRECTORIES:
        remove_directory(PROJECT_ROOT / directory)

    for pattern in GENERATED_FILE_PATTERNS:
        for path in PROJECT_ROOT.glob(pattern):
            remove_file(path)

    print()
    print("Done.")
    print()
    print("Kept:")
    print("- assets/images/")
    print("- data/fia_documents/")
    print("- docs/")
    print("- tests/")


if __name__ == "__main__":
    main()