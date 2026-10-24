"""Reconcile old tuning decisions against the current inspection ledger.

Writes a separate audit; original benchmark reports are never rewritten.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from src.inspection_ledger import discover_reports, inspected_race_keys


def audit(root, output):
    root, output = Path(root), Path(output)
    paths = discover_reports(root)
    known = inspected_race_keys(paths)
    rows = []
    for path in paths:
        report = json.loads(path.read_text(encoding='utf-8'))
        if 'holdout_races_evaluated' not in report:
            continue
        holdout = {tuple(k) for k in report['holdout_races_evaluated']}
        # Current reuse policy includes this report's own already viewed results.
        unseen = holdout - known
        rows.append({'report': str(path.resolve()),
            'report_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'original_unseen_count': report.get('unseen_holdout_race_count'),
            'original_gate_passed': report.get('promotion_gate_passed'),
            'unseen_on_reuse': len(unseen),
            'eligible_as_fresh_confirmation': len(unseen) >= 6,
            'interpretation': 'Previously inspected results are diagnostic on reuse, regardless of original gate.'})
    result = {'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'inspected_races': [list(k) for k in sorted(known)], 'tuning_reviews': rows,
        'inspection_reports_sha256': {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        'source_sha256': hashlib.sha256((root/'src/inspection_ledger.py').read_bytes()).hexdigest(),
        'activated': False, 'original_reports_changed': False}
    output.mkdir(parents=True, exist_ok=False)
    (output/'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.workspace, args.output_dir)
    print(json.dumps({'inspected_races': len(result['inspected_races']),
                      'tuning_reviews': result['tuning_reviews']}, indent=2))


if __name__ == '__main__':
    main()
