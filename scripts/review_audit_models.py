"""Refit audited historical candidates into new directories without activating them."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import warnings

import pandas as pd

from src.historical_model import train_historical_models


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def review(audit_dir, output_dir):
    audit_dir, output_dir = Path(audit_dir), Path(output_dir)
    audit = json.loads((audit_dir/'audit_manifest.json').read_text(encoding='utf-8'))
    old_candidates = pd.read_csv(audit_dir/'training_model_audit.csv')
    original = pd.read_csv(audit_dir/'training_validation_comparisons.csv')
    desktop = Path(audit['source_roots']['desktop'])
    output_dir.mkdir(parents=True, exist_ok=False)
    reports, inputs = [], {}
    for old in old_candidates.itertuples():
        job = desktop/'outputs/app_runs'/old.job
        snapshot = job/'training_inputs'
        snapshot_manifest = json.loads((snapshot/'snapshot_manifest.json').read_text(encoding='utf-8'))
        result = json.loads((job/'training_result.json').read_text(encoding='utf-8'))
        protected = {str(job/'candidate'/name): value for name, value in result['artifact_sha256'].items()}
        protected.update({str(snapshot/name): value for name, value in snapshot_manifest['assembled_csv_sha256'].items()})
        for filename, checksum in protected.items():
            if sha(filename) != checksum:
                raise ValueError(f'Original audited artifact/input checksum changed: {filename}')
        inputs.update(protected)
        for finish_target in ['absolute', 'grid_residual']:
            print(f'Refitting {old.job}: {finish_target}', flush=True)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                artifacts = train_historical_models(snapshot, output_dir/old.job/finish_target,
                                                    finish_target=finish_target)
            metrics = json.loads(Path(artifacts.metrics).read_text(encoding='utf-8'))
            reports.append({'original_job': old.job, 'finish_target': finish_target,
                'validation_years': ','.join(map(str, metrics['validation_years'])),
                'old_finish_mae': old.finish_mae, 'new_finish_mae': metrics['finish_mae'],
                'qualifying_baseline_mae': metrics['qualifying_baseline_mae'],
                'coherent_order_mae': metrics['finish_order_mae'],
                'old_corrected_dnf_brier': old.audited_dnf_brier, 'new_dnf_brier': metrics['dnf_brier'],
                'dnf_prior_baseline_brier': metrics['dnf_prior_baseline_brier'],
                'known_dnf_validation_rows': metrics['dnf_validation_known_rows'],
                'unknown_dnf_validation_rows': metrics['dnf_validation_unknown_rows'],
                'excluded_dns_disqualified_rows': metrics['excluded_dns_or_disqualified_rows'],
                'activated': False, 'promotion_eligible': False,
                'warnings': list(dict.fromkeys(str(w.message) for w in caught)),
                'candidate_dir': str(Path(artifacts.metrics).parent.resolve())})
    for filename, checksum in inputs.items():
        if sha(filename) != checksum:
            raise ValueError(f'Original artifact modified during review: {filename}')
    rows = pd.DataFrame(reports)
    rows.to_csv(output_dir/'candidate_comparison.csv', index=False)
    # Carry forward every inspected actual outcome so later benchmarks cannot
    # quietly label audit/training validation races as untouched confirmation.
    inspected = set(map(tuple, original[['Year', 'Round']].drop_duplicates().to_numpy()))
    scores = pd.read_csv(audit_dir/'all_run_metrics.csv')
    inspected.update(map(tuple, scores[['year', 'round']].drop_duplicates().to_numpy()))
    inspection = {'evaluated_races': [[int(y), int(r)] for y, r in sorted(inspected)],
                  'source_audit_manifest_sha256': sha(audit_dir/'audit_manifest.json')}
    (output_dir/'inspected_races.json').write_text(json.dumps(inspection, indent=2), encoding='utf-8')
    root = Path(__file__).resolve().parents[1]
    report = {'activated': False, 'promotion_eligible': False,
        'validation_type': 'previously inspected retrospective diagnostic; not fresh validation',
        'comparability': 'DNS/disqualified rows excluded after correction; old/new finish denominators can differ.',
        'candidates': reports, 'protected_inputs_sha256': inputs,
        'source_sha256': {name: sha(root/name) for name in ['src/historical_model.py', 'src/result_status.py',
                                                         'scripts/review_audit_models.py']}}
    (output_dir/'review.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(rows[['validation_years', 'finish_target', 'new_finish_mae', 'qualifying_baseline_mae',
                'new_dnf_brier', 'dnf_prior_baseline_brier']].round(4).to_string(index=False))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    output = args.output_dir or Path('outputs/model_revision')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    review(args.audit_dir, output)


if __name__ == '__main__':
    main()
