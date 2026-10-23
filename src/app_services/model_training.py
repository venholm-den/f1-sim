"""Offline candidate training from immutable historical-library session versions."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.app_services import historical_library as library
from src.app_services.simulation_jobs import write_json


def options(payload):
    if not isinstance(payload, dict):
        raise ValueError('Select downloaded detailed seasons for training.')
    return {'years': library.options({'years': payload.get('years', [])})['years'],
            'enriched': bool(payload.get('enriched', False))}


def selection(root, years, enriched=False):
    pairs, skipped = {}, []
    for year in years:
        for pointer in sorted((library.library_root(root)/str(year)/'detailed').glob('*/session.json')):
            saved = library.read_json(pointer)
            if saved.get('session') not in (('Q', 'R', 'FP1', 'FP2', 'FP3') if enriched else ('Q', 'R')):
                continue
            if not library.complete(pointer.parent):
                skipped.append({'year': year, 'event': saved.get('event', pointer.parent.name), 'reason': 'Missing or damaged session files'})
                continue
            key = (int(saved['year']), int(saved['round']))
            pair = pairs.setdefault(key, {})
            if saved['session'] in pair:
                raise ValueError('Duplicate archive sessions for the same season and round. Review the library before training.')
            pair[saved['session']] = {'folder': str(pointer.parent), 'manifest': saved}
    selected = []
    for (year, round_number), pair in sorted(pairs.items()):
        event = next(iter(pair.values()))['manifest']['event']
        if not {'Q', 'R'}.issubset(pair):
            skipped.append({'year': year, 'event': event, 'reason': 'Download both Q and R detailed sessions'})
            continue
        q, r = pair['Q']['manifest'], pair['R']['manifest']
        if r.get('venue', {}).get('race_quality', {}).get('training_eligible') is False:
            skipped.append({'year': year, 'event': event,
                'reason': 'Aborted classified race retained for audit; excluded from normal race training'})
            continue
        if q['event'] != r['event']:
            raise ValueError('Qualifying and race event identities disagree in the archive.')
        if not all(any(info['table'] == table and info['rows'] > 0 for info in q['files'].values())
                   for table in ('laps', 'results')) or not any(
                info['table'] == 'results' and info['rows'] > 0 for info in r['files'].values()):
            skipped.append({'year': year, 'event': event, 'reason': 'Qualifying laps, official Q classification or race classifications are unavailable'})
            continue
        selected.append({'year': year, 'round': round_number, 'event': event, 'sessions': pair})
    return {'years': years, 'races': selected, 'skipped': skipped, 'enriched': enriched}


def state(root):
    seasons = library.inventory(root)['seasons']
    years = sorted({row['year'] for row in seasons if row['mode'] == 'detailed'}, reverse=True)
    rows = []
    for year in years:
        plan = selection(root, [year])
        rows.append({'year': year, 'paired_races': len(plan['races']), 'skipped_races': len(plan['skipped'])})
    return {'seasons': rows, 'minimum_races': 3,
            'validation_policy': 'Latest selected season held out; with one season, its last 25% of races are held out.'}


def prepare(root, payload):
    config = options(payload)
    plan = selection(root, config['years'], config['enriched'])
    if len(plan['races']) < 3:
        raise ValueError('Training needs at least three matched Q + R races. Download detailed qualifying and race sessions; classifications alone cannot train this model.')
    return plan


def train(root, folder, plan):
    from src.historical_model import train_historical_models

    snapshot = folder/'training_inputs'
    snapshot.mkdir(exist_ok=False)
    sources, tables = [], {}
    total = len(plan['races'])
    for index, race in enumerate(plan['races'], 1):
        write_json(folder/'training_progress.json', {'stage': 'Checking and snapshotting archive', 'processed': index-1, 'total': total})
        print(f"Snapshotting {race['year']} {race['event']} ({index}/{total})", flush=True)
        for session, partition in race['sessions'].items():
            source_folder, saved = Path(partition['folder']), partition['manifest']
            if not source_folder.resolve().is_relative_to(library.library_root(root).resolve()):
                raise ValueError('Training source is outside this workspace archive.')
            wanted = {'laps', 'results', 'weather', 'race_control'} if session == 'Q' else {'results'}
            if plan.get('enriched'):
                wanted = {'laps', 'weather', 'race_control', 'race_control_messages'} if session != 'R' else {'results'}
                if session == 'Q':
                    wanted.add('results')
            for file, info in library.partition_files(source_folder, saved):
                if info['table'] not in wanted:
                    continue
                copied = snapshot/f"{race['year']}_{race['round']}_{session}_{info['table']}.csv.gz"
                shutil.copyfile(file, copied)
                if library.sha256(copied) != info['sha256']:
                    raise ValueError('Archive checksum failed. Resume the download to repair the session before training.')
                frame = pd.read_csv(copied)
                if session == 'R' and ('Status' not in frame or frame.Status.fillna('').astype(str).str.strip().eq('').any()):
                    raise ValueError('Race outcomes have unknown statuses. Repair the archive before training DNF probabilities.')
                for name, value in [('Year', race['year']), ('Round', race['round']), ('Event', race['event']), ('Session', session)]:
                    if name not in frame or not frame[name].astype(str).eq(str(value)).all():
                        raise ValueError('Session metadata in the archived table disagrees with its provenance.')
                tables.setdefault(info['table'], []).append(frame)
                sources.append({'year': race['year'], 'round': race['round'], 'session': session,
                                'source': str(file), 'snapshot': copied.name, 'sha256': info['sha256'], 'rows': len(frame)})
    for table, frames in tables.items():
        pd.concat(frames, ignore_index=True).to_csv(snapshot/f'{library.EXPORT_NAMES[table]}.csv', index=False)
    confirmed = Path(root)/'data/prediction_enrichment/retirement_causes.csv'
    if plan.get('enriched') and confirmed.is_file():
        destination = snapshot/'retirement_causes.csv'
        shutil.copyfile(confirmed, destination)
        sources.append({'source': str(confirmed), 'snapshot': destination.name,
                        'sha256': library.sha256(destination), 'table': 'confirmed_retirement_causes'})
    write_json(folder/'training_progress.json', {'stage': 'Fitting models and evaluating later races', 'processed': total, 'total': total})
    print('Fitting on earlier races; evaluating held-out later race outcomes. Previously inspected races are diagnostic only.', flush=True)
    write_json(snapshot/'snapshot_manifest.json', {'sources': sources, 'assembled_csv_sha256': {
        path.name: library.sha256(path) for path in snapshot.glob('*.csv')}})
    candidate = folder/'candidate'
    artifacts = train_historical_models(snapshot, candidate, enriched=plan.get('enriched', False))
    metrics = library.read_json(artifacts.metrics)
    files = {path.name: library.sha256(path) for path in candidate.iterdir() if path.is_file()}
    report = {'status': 'complete', 'candidate_dir': str(candidate), 'years': plan['years'],
              'created_at_utc': datetime.now(timezone.utc).isoformat(), 'metrics': metrics,
              'sources': sources, 'skipped_races': plan['skipped'], 'artifact_sha256': files,
              'activated': False, 'validation_type': 'retrospective chronological holdout',
              'limitations': 'Cached feeds may contain retrospective revisions. This holdout does not prove improvement over the live simulation. Races without complete official Q classification are excluded; missing Q timing is imputed. Mixed seasons may span different regulations. Repeatedly inspecting the same holdout does not provide fresh validation.'}
    write_json(folder/'training_result.json', report)
    write_json(folder/'training_progress.json', {'stage': 'Candidate saved for review', 'processed': total, 'total': total})
    dnf_brier = 'unavailable' if metrics['dnf_brier'] is None else f"{metrics['dnf_brier']:.4f}"
    prior_brier = 'unavailable' if metrics['dnf_prior_baseline_brier'] is None else f"{metrics['dnf_prior_baseline_brier']:.4f}"
    print(f"Candidate saved: {candidate}\nFinish MAE: {metrics['finish_mae']:.3f}; qualifying baseline: {metrics['qualifying_baseline_mae']:.3f}\nDNF Brier: {dnf_brier}; training-rate baseline: {prior_brier}\nLive models and forecast settings are unchanged.", flush=True)
    return report


def result(folder):
    report = library.read_json(folder/'training_result.json')
    if not report:
        return None
    candidate = folder/'candidate'
    report['verified'] = all((candidate/name).is_file() and library.sha256(candidate/name) == digest
                             for name, digest in report['artifact_sha256'].items())
    return report
