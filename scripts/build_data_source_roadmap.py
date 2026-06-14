from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.data_sources.fia_documents import create_example_fia_document_index
from src.data_sources.roadmap import (
    describe_openf1_endpoints,
    save_data_source_roadmap,
)


def main() -> None:
    roadmap_path = save_data_source_roadmap()
    fia_index_path = create_example_fia_document_index()

    print("Data-source roadmap created:")
    print(f"- roadmap: {roadmap_path}")
    print(f"- FIA document index: {fia_index_path}")
    print()
    print("OpenF1 endpoints scaffolded:")
    print(describe_openf1_endpoints().to_string(index=False))


if __name__ == "__main__":
    main()