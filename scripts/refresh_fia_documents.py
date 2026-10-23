"""Update FIA listings and extract explicit grids/penalties, preserving source captures."""
import argparse
import json
from pathlib import Path

from portable_app.instance_lock import workspace_lock
from src.data_sources.fia_sync import refresh


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--year',type=int)
    parser.add_argument('--all-events',action='store_true')
    parser.add_argument('--max-documents',type=int,default=24)
    parser.add_argument('--pdf-python',type=Path)
    args = parser.parse_args()
    if not 1<=args.max_documents<=500:
        parser.error('Use 1-500 documents per run.')
    with workspace_lock(args.root):
        result = refresh(args.root,year=args.year,force=True,all_events=args.all_events,
            max_documents=args.max_documents,pdf_python=args.pdf_python)
    print(json.dumps(result,indent=2))
    return 1 if result['status']=='failed' else 0


if __name__=='__main__':
    raise SystemExit(main())
