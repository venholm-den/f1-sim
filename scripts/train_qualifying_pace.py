"""Fit an inactive post-Q pace artifact using strictly earlier cached races."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from src.accuracy_benchmark import load_cached_races, session_input_frame
from src.qualifying_pace import fit_qualifying_pace
from src.venues import venue_for_context


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, default=Path('data/cache'))
    parser.add_argument('--years', nargs='+', type=int, default=[2025, 2026])
    parser.add_argument('--target-year', type=int, required=True)
    parser.add_argument('--target-round', type=int, required=True)
    parser.add_argument('--event', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--qualifying-results', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite an existing pace artifact.')
    races, failures = load_cached_races(args.cache_dir.resolve(), args.years)
    if args.qualifying_results:
        from src.qualifying_archive import attach_archive
        races = attach_archive(races, args.qualifying_results)
    history = []
    hashes = {}
    for race in races:
        if race.key >= (args.target_year, args.target_round):
            continue
        context = dict(year=race.year, round=race.round, event=race.event)
        context['venue'] = venue_for_context(context, session=race.sessions['R'])
        history.append((race.sessions.get('Q'), race.sessions['R'], context))
        for code in ('Q', 'R'):
            if code not in race.sessions:
                continue
            for name in ('laps', 'results', 'weather_data'):
                hashes[f'{race.year}/{race.round}/{code}/{name}'] = hashlib.sha256(
                    session_input_frame(race.sessions[code], name).to_csv().encode()).hexdigest()
    artifact = fit_qualifying_pace(history, dict(year=args.target_year, round=args.target_round, event=args.event))
    root = Path(__file__).resolve().parents[1]
    artifact['input_sha256'] = hashes
    artifact['source_sha256'] = {name: hashlib.sha256((root/name).read_bytes()).hexdigest()
        for name in ('src/qualifying_pace.py', 'src/qualifying_features.py', 'src/qualifying_archive.py',
                     'src/features.py', 'src/model_config.py')}
    artifact['load_failures'] = failures
    artifact['promotion_approved'] = False
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(artifact, handle, indent=2, allow_nan=False)
    print(json.dumps({'output': str(args.output.resolve()), 'observations': artifact['observations'],
                      'races': artifact['training_races'], 'activated': False}))


if __name__ == '__main__':
    main()
