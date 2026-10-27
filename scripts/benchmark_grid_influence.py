"""Offline archive replay: fit mappings through 2024; score later races separately."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from src.accuracy_benchmark import ReplayRace, build_replay_inputs, simple_baseline, evaluate_forecast
from src.circuit_calibration import calibration_venue, observations, sha256
from src.feature_ablation_benchmark import evaluate_with_dnf
from src.grid_influence import MAPPINGS, mapped_difficulty, select_mapping
from src.simulate import simulate_races
from src.retirement_evidence import apply_outcome_evidence


def load_archive(workspace, years):
    """No remote requests/cache mutation; export units are preserved explicitly."""
    races, sources, failures, q_audit = {}, [], [], []
    for path in sorted((Path(workspace)/'data/historical_library').glob('*/detailed/*/session.json')):
        m = json.loads(path.read_text(encoding='utf-8'))
        if m.get('year') not in years or m.get('status') != 'complete' or m.get('session') not in ('R', 'Q', 'FP2'):
            continue
        code = m['session']; key = m['year'], m['round']
        try:
            if m.get('venue', {}).get('race_quality', {}).get('training_eligible') is False:
                raise ValueError('aborted classification')
            tables = {}
            for name, info in m['files'].items():
                if info.get('table') not in ('laps', 'results', 'weather_samples'):
                    continue
                # Windows-written manifests use backslashes; resolve them on any OS.
                file = (path.parent/name.replace('\\', '/')).resolve()
                if (not file.is_relative_to(path.parent.resolve()) or not file.is_file()
                        or file.stat().st_size != info['bytes'] or sha256(file) != info['sha256']):
                    raise ValueError('Archive table checksum/path mismatch')
                if info['table'] in tables:
                    raise ValueError('Duplicate archive table')
                tables[info['table']] = pd.read_csv(file)
                sources.append({'path': str(file), 'sha256': info['sha256']})
            laps, results = tables['laps'], tables['results']
            if laps.empty or results.empty:
                raise ValueError('Empty laps/results')
            if code == 'R':
                results = apply_outcome_evidence(results, m)
            if 'TrackStatus' in laps:
                laps['TrackStatus'] = laps.TrackStatus.astype(str).str.removesuffix('.0')
            # Some grid feature fallbacks expect FastF1 timedelta columns.
            laps['LapTime'] = pd.to_timedelta(laps.LapTimeSeconds, unit='s')
            if code == 'Q':
                ranks = pd.to_numeric(results.Position, errors='coerce')
                valid = (not results.Abbreviation.isna().any() and not results.Abbreviation.duplicated().any()
                         and sorted(ranks.dropna()) == list(range(1, len(results)+1)))
                q_audit.append({'year': m['year'], 'round': m['round'], 'event': m['event'],
                    'drivers': len(results), 'missing_positions': results.loc[ranks.isna(), 'Abbreviation'].tolist(),
                    'duplicate_positions': ranks[ranks.notna() & ranks.duplicated(keep=False)].tolist(),
                    'complete_unique_classification': valid, 'manifest_path': str(path.resolve()),
                    'manifest_sha256': sha256(path), 'action': 'eligible' if valid else 'excluded_Q_only_no_rank_imputation'})
                if not valid:
                    raise ValueError('Q classification lacks complete unique official ranks')
            venue, provenance = calibration_venue(m)
            event = pd.Series({'RoundNumber': m['round'], 'EventName': m['event'],
                'Location': m.get('venue', {}).get('feed_location')})
            session = SimpleNamespace(laps=laps, results=results,
                weather_data=tables.get('weather_samples', pd.DataFrame()), event=event, session_info={})
            entry = races.setdefault(key, {'event': m['event'], 'sessions': {}, 'venues': {}})
            if code in entry['sessions'] or entry['event'] != m['event']:
                raise ValueError('Ambiguous duplicate archive session')
            entry['sessions'][code] = session
            entry['venues'][code] = venue
        except (ValueError, KeyError, OSError) as exc:
            failures.append({k: m[k] for k in ('year', 'round', 'event', 'session')} | {'reason': str(exc)})
    output, venues = [], {}
    for key, value in sorted(races.items()):
        if 'R' not in value['sessions']:
            continue
        output.append(ReplayRace(*key, value['event'], value['sessions']))
        venues[key] = value['venues']
    return output, venues, sources, failures, q_audit


def run(workspace, output, *, years, fit_through=2024, n_sims=1000, seeds=(42, 123, 777)):
    if n_sims < 100 or not seeds or fit_through >= max(years):
        raise ValueError('Need >=100 simulations, seeds, and later scoring years')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    history, history_excluded = observations(workspace, years)
    races, venues, source_files, failures, q_audit = load_archive(workspace, years)
    pd.DataFrame(q_audit).to_csv(output/'qualifying_coverage.csv', index=False)
    source_root = Path(__file__).resolve().parents[1]
    source_paths = [*sorted((source_root/'src').rglob('*.py')), Path(__file__), source_root/'data/track_profiles.csv',
                    source_root/'data/team_power_units.csv']
    protocol = {'schema_version': 1, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'activated': False, 'promotion_approved': False, 'mappings': list(MAPPINGS),
        'stages': ['PRE', 'FP2', 'Q'], 'fit_through_year': fit_through, 'seeds': list(seeds), 'n_sims': n_sims,
        'selection_loss': 'finish MAE plus top10 Brier; seeds averaged then races weighted equally',
        'mapping_policy': {'uniform_055': '0.55 everywhere', 'active_times_125': 'min(0.95, 1.25 * active)',
            'earlier_order_proxy': 'clip(0.55 * earlier pooled rate / earlier shrunken local rate, .25, .90); active fallback below two local races'},
        'development_races': [list(r.key) for r in races if r.year <= fit_through],
        'attempted_races': [list(r.key) for r in races],
        'input_sources': source_files,
        'source_sha256': {str(p.resolve()): sha256(p) for p in source_paths},
        'limitations': ['All historical races inspected: later scores are diagnostic, never fresh validation.',
            'Retrospective archives may include later corrections; publication times are not attested.',
            'PRE roster is the latest baseline assumption; mismatched target coverage is skipped.',
            'Each stage is compared on complete matched episodes only.',
            'Order-change mapping is a declared statistical proxy; no physical overtake calibration claimed.',
            'Stage-specific development selection is not jointly optimised with other shadow models.']}
    (output/'protocol.json').write_text(json.dumps(protocol, indent=2, allow_nan=False), encoding='utf-8')
    rows, predictions, skipped, baseline_rows, episodes = [], [], [], [], []

    def evaluate(race, index, stage, split, mappings):
        current = None if stage == 'PRE' else race.sessions.get(stage)
        metadata = dict(year=race.year, round=race.round, event=race.event, session=stage)
        metadata['venue'] = venues[race.key].get(stage, venues[race.key]['R'])
        if stage != 'PRE' and current is None:
            raise ValueError('Session absent or invalid classification')
        features, track, weather = build_replay_inputs(current, races[:index], metadata=metadata)
        baseline, _ = evaluate_forecast(simple_baseline(features, races[:index], 'grid_order'), race.sessions['R'].results)
        stage_rows, stage_predictions = [], []
        for mapping in mappings:
            difficulty, evidence = mapped_difficulty(mapping, track['overtaking_difficulty'], metadata, history)
            for seed in seeds:
                summary, _, _ = simulate_races(features, n_sims=n_sims, seed=seed,
                    overtaking_difficulty=difficulty, weather_modifiers=weather)
                metrics, data = evaluate_with_dnf(summary, race.sessions['R'].results)
                identity = {k: metadata[k] for k in ('year', 'round', 'event', 'session')} | {
                    'mapping': mapping, 'split': split, 'seed': seed, 'difficulty': difficulty}
                stage_rows.append(identity | metrics)
                stage_predictions.append(data.assign(**identity))
        rows.extend(stage_rows); predictions.extend(stage_predictions)
        baseline_rows.append({k: metadata[k] for k in ('year', 'round', 'event', 'session')} |
                             {'split': split, **baseline})
        episodes.append({k: metadata[k] for k in ('year', 'round', 'event', 'session')} |
            {'split': split, 'grid_source': sorted(features.grid_source.unique().tolist()),
             'weather_source': weather.get('weather_source', 'not_observed_before_stage')})

    for later in (False, True):
        if later:
            frame = pd.DataFrame(rows)
            selected = {stage: select_mapping(frame, stage) for stage in protocol['stages']}
            # Freeze the stage choices before inspecting any later outcome score.
            (output/'selection.json').write_text(json.dumps({'selected_on_development': selected,
                'created_at_utc': datetime.now(timezone.utc).isoformat(), 'activated': False,
                'protocol_sha256': sha256(output/'protocol.json')}, indent=2), encoding='utf-8')
            print('Development selection: '+json.dumps(selected), flush=True)
        for index, race in enumerate(races):
            if index < 2 or (race.year > fit_through) != later:
                continue
            split = 'previously_seen_diagnostic' if later else 'development'
            for stage in protocol['stages']:
                mappings = list(dict.fromkeys(['active_profile', selected[stage]])) if later else MAPPINGS
                try:
                    evaluate(race, index, stage, split, mappings)
                    print(f'{race.year} R{race.round} {stage}: {split} complete', flush=True)
                except (ValueError, KeyError) as exc:
                    skipped.append(dict(year=race.year, round=race.round, event=race.event, session=stage,
                        split=split, reason=str(exc)))
    frame = pd.DataFrame(rows)
    columns = ['finish_mae', 'win_brier', 'podium_brier', 'top10_brier', 'dnf_brier', 'loss']
    race_metrics = frame.groupby(['split', 'session', 'mapping', 'year', 'round'], as_index=False)[columns].mean()
    summary = race_metrics.groupby(['split', 'session', 'mapping'], as_index=False).agg(
        races=('round', 'count'), **{c: (c, 'mean') for c in columns})
    candidate = {'model': 'grid_influence_v1', 'activated': False, 'promotion_approved': False,
        'selected_on_development': selected, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'protocol_sha256': sha256(output/'protocol.json'), 'history_observations': history,
        'source_sha256': {name: sha256(source_root/'src'/name) for name in ('grid_influence.py', 'circuit_calibration.py', 'venues.py')},
        'minimum_fresh_races_per_stage': 6, 'minimum_loss_improvement': .05,
        'no_regression': ['win_brier', 'podium_brier', 'top10_brier', 'dnf_brier']}
    (output/'candidate.json').write_text(json.dumps(candidate, indent=2, allow_nan=False), encoding='utf-8')
    frame.to_csv(output/'seed_metrics.csv', index=False)
    race_metrics.to_csv(output/'race_metrics.csv', index=False)
    summary.to_csv(output/'summary.csv', index=False)
    pd.concat(predictions, ignore_index=True).to_csv(output/'predictions.csv', index=False)
    pd.DataFrame(baseline_rows).to_csv(output/'grid_baseline.csv', index=False)
    report = protocol | {'completed_at_utc': datetime.now(timezone.utc).isoformat(),
        'selected_on_development': selected, 'evaluated_races': sorted({(r['year'], r['round']) for r in rows}),
        'summary': summary.to_dict('records'), 'skipped': skipped, 'load_failures': failures,
        'qualifying_audit': q_audit, 'history_excluded': history_excluded, 'episodes': episodes,
        'fresh_validation_race_count': 0, 'promotion_gate_passed': False,
        'candidate_sha256': sha256(output/'candidate.json'),
        'artifact_sha256': {p.name: sha256(p) for p in output.iterdir() if p.is_file()}}
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--years', type=int, nargs='+', default=list(range(2021, 2027)))
    parser.add_argument('--fit-through', type=int, default=2024)
    parser.add_argument('--n-sims', type=int, default=1000)
    parser.add_argument('--seeds', type=int, nargs='+', default=[42, 123, 777])
    args = parser.parse_args()
    report = run(args.workspace, args.output_dir, years=sorted(set(args.years)), fit_through=args.fit_through,
                 n_sims=args.n_sims, seeds=tuple(dict.fromkeys(args.seeds)))
    print(json.dumps({'output': str(args.output_dir.resolve()), 'selected': report['selected_on_development'],
        'summary': report['summary']}, indent=2))


if __name__ == '__main__':
    main()
