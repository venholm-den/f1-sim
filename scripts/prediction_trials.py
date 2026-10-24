"""Register, capture and score prospective model trials without Discord."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from portable_app.instance_lock import workspace_lock
from src.app_services.prediction_trials import (CONFIG, ROOT, capture_trial,
    comparison_report, register_suite, renew_suite, read_suite, score_trials)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--register',action='store_true',help='Pin the existing ensemble and enable local shadow trials.')
    parser.add_argument('--renew-existing', action='store_true',
                        help='Create a separate cohort retaining the enabled suite arms and inspection ledger.')
    parser.add_argument('--verify-only', action='store_true',
                        help='Verify enabled suite sources/inputs without capture, network access or new reports.')
    parser.add_argument('--ensemble-config',type=Path,default=Path('config/stage_ensemble_shadow.json'))
    parser.add_argument('--inspected-reports',type=Path,nargs='*',default=[],
                        help='Carry inspected benchmark outcomes forward when registering a new suite.')
    parser.add_argument('--extended-models', action='store_true', help='Add agent, pit, survival and Q pace shadow arms.')
    parser.add_argument('--history-packet', type=Path, help='Immutable candidate_history.json.gz snapshot for survival/Q pace arms.')
    parser.add_argument('--grid-candidate', type=Path, help='Inactive stage-specific grid mapping selected by chronological benchmark.')
    parser.add_argument('--forecast-folder',type=Path,help='Capture a specified eligible frozen forecast.')
    parser.add_argument('--latest',action='store_true',help='Capture the latest verified automated prospective forecast.')
    parser.add_argument('--score',action='store_true',help='Score completed official-result jobs, without fetching or posting.')
    args=parser.parse_args(); root=args.workspace.resolve(); results={}
    if args.verify_only:
        if any((args.register, args.renew_existing, args.latest, args.score, args.forecast_folder)):
            parser.error('--verify-only cannot be combined with mutations or capture/scoring.')
        suite = read_suite(root)
        print(json.dumps({'status': 'verified' if suite else 'disabled',
                          'suite_sha256': suite[2] if suite else None}))
        return
    if args.renew_existing and (args.register or args.extended_models or args.history_packet or args.grid_candidate):
        parser.error('--renew-existing retains the old protocol; do not combine it with registration/model options.')
    with workspace_lock(root):
        if args.register or args.renew_existing:
            if args.renew_existing:
                config=renew_suite(root, root/args.ensemble_config,
                                   inspected_reports=[root/path for path in args.inspected_reports])
            else:
                config=register_suite(root,root/args.ensemble_config,
                                  inspected_reports=[root/path for path in args.inspected_reports],
                                  extended_models=args.extended_models,
                                  history_path=root/args.history_packet if args.history_packet else None,
                                  grid_candidate_path=root/args.grid_candidate if args.grid_candidate else None)
            path=root/CONFIG
            if path.is_file():
                backup=root/ROOT/'config_backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ.json')
                backup.parent.mkdir(parents=True,exist_ok=True)
                backup.write_bytes(path.read_bytes())
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(config,indent=2),encoding='utf-8')
            results['registered']=config
        forecast=args.forecast_folder
        if args.latest:
            from src.app_services.beta import verified_snapshot
            candidates=[]
            for path in (root/'outputs/app_runs').glob('*/frozen/manifest.json'):
                try:
                    manifest=verified_snapshot(path.parent.parent)
                    if manifest['category']=='prospective':
                        candidates.append((manifest['created_at_utc'],path.parent.parent))
                except (ValueError,OSError,KeyError):
                    continue
            if not candidates:
                raise ValueError('No verified prospective forecast is available.')
            forecast=max(candidates,key=lambda row:row[0])[1]
        if forecast:
            results['capture']=capture_trial(root,root/forecast)
        if args.score:
            results['scoring']=score_trials(root)
        results['report']=comparison_report(root)
    print(json.dumps(results,indent=2,allow_nan=False))


if __name__=='__main__':
    main()
