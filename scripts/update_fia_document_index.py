from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_sources.fia_documents import (  # noqa: E402
    FIA_DOCUMENT_INDEX_PATH,
    fia_f1_documents_url,
    update_fia_document_index,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch FIA Formula 1 document listings into the local FIA index."
    )
    parser.add_argument("--year", type=int, required=True, help="F1 season year.")
    parser.add_argument(
        "--season-url",
        default="",
        help="Override the FIA decision-documents season URL.",
    )
    parser.add_argument(
        "--event",
        default="",
        help='Optional exact event filter, for example "Hungarian Grand Prix".',
    )
    parser.add_argument(
        "--index-path",
        default=FIA_DOCUMENT_INDEX_PATH,
        help="CSV index path to update.",
    )
    parser.add_argument(
        "--enrich-pdfs",
        action="store_true",
        help="Download selected PDFs and parse grid/classification/stewards rows.",
    )
    parser.add_argument(
        "--driver-map",
        default="",
        help="Optional CSV with car_number,driver,team columns for PDF enrichment.",
    )
    parser.add_argument(
        "--cache-dir",
        default="data/fia_documents/cache",
        help="Directory for cached FIA PDFs when --enrich-pdfs is used.",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds.")
    args = parser.parse_args()

    season_url = args.season_url or fia_f1_documents_url(args.year)
    result = update_fia_document_index(
        year=args.year,
        path=args.index_path,
        season_url=season_url,
        event=args.event or None,
        enrich_pdfs=args.enrich_pdfs,
        driver_map_path=args.driver_map or None,
        cache_dir=args.cache_dir,
        timeout=args.timeout,
    )

    print(f"Updated: {result['path']}")
    print(f"FIA listings matched: {result['listings']}")
    print(f"Rows considered: {result['rows_written']}")
    print(f"PDF-enriched rows: {result['enriched_rows']}")

    for warning in result["warnings"]:
        print(f"Warning: {warning}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
