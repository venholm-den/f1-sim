"""Repair missing Q/R pairs, then audit calendar and candidate-training coverage.

Only sessions named as missing by the latest training selection are requested.
Complete partitions are skipped; existing versions and trained candidates remain.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from src.app_services import historical_library as library
from src.app_services.model_training import selection
from src.app_services.simulation_jobs import write_json


def audit(root, years, calendars):
    selected = selection(root, years, enriched=True)
    seasons = []
    for year in years:
        races = [race for race in selected['races'] if race['year'] == year]
        expected = {task['round'] for task in calendars[year] if task['session'] == 'R'}
        paired = {race['round'] for race in races}
        seasons.append({'year': year, 'completed_calendar_races': len(expected),
                        'training_pairs': len(races), 'training_excluded_rounds': sorted(expected-paired),
                        'practice_sessions': sum(len(set(race['sessions']) & {'FP1', 'FP2', 'FP3'}) for race in races)})
    return {'seasons': seasons, 'paired_races': len(selected['races']), 'skipped': selected['skipped'],
            'sessions': [{'year': race['year'], 'round': race['round'], 'event': race['event'],
                'sources': {code: {'manifest_sha256': library.sha256(Path(partition['folder'])/'session.json'),
                    'table_rows': {info['table']: info['rows'] for info in partition['manifest']['files'].values()
                                   if info['table'] in {'laps', 'results', 'weather', 'race_control'}}}
                    for code, partition in race['sessions'].items()}} for race in selected['races']]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--years', type=int, nargs='+', default=list(range(2021, 2027)))
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--repair', action='store_true')
    args = parser.parse_args()
    root = args.workspace.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    # Avoid competing writes with an app download or a training snapshot.
    for path in (root/'outputs/app_runs').glob('*/job.json'):
        job = library.read_json(path)
        if job.get('kind') in {'historical_download', 'historical_training'} and job.get('status') in {'running', 'cancelling'}:
            raise ValueError('Finish the active archive/training job before repairing coverage.')
    from src.app_services.f1_account import configure_worker_auth
    configure_worker_auth()
    # An independent cache avoids touching a damaged or actively used app HTTP
    # database. Completed archive partitions are still checked/skipped in root.
    provider_workspace = output/'provider_workspace'
    calendars = {year: library.discover(provider_workspace, year, 'detailed', ['Q', 'R']) for year in args.years}
    before = audit(root, args.years, calendars)
    write_json(output/'coverage_before.json', before)
    missing = {(row['year'], row['event']) for row in before['skipped']
               if row['reason'] == 'Download both Q and R detailed sessions'}
    results = []
    if args.repair:
        for year in args.years:
            tasks = [task for task in calendars[year] if (year, task['event']) in missing]
            if not tasks:
                continue
            folder = output/f'repair_{year}'
            folder.mkdir()
            result = library.download(root, folder, {'years': [year], 'mode': 'detailed',
                'sessions': ['Q', 'R'], 'telemetry': False}, discover_fn=lambda *_, tasks=tasks: tasks)
            results.append(result)
    after = audit(root, args.years, calendars)
    write_json(output/'coverage_after.json', after)
    report = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'workspace': str(root),
              'paired_before': before['paired_races'], 'paired_after': after['paired_races'],
              'seasons': after['seasons'], 'remaining_skips': after['skipped'], 'downloads': results,
              'model_activated': False, 'limitations':
              'Paired files do not establish complete usable driver coverage or predictive accuracy. '
              'Candidates still need chronological, driver-coverage and prospective validation.'}
    write_json(output/'report.json', report)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
