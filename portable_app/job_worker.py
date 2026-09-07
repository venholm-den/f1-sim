"""Child-process entry point for cancellable simulation jobs."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import shutil
from pathlib import Path

import pandas as pd

from scripts.run_lap_experiments import prepare, verify, sha256
from src.simulink_export import export_simulink_inputs
from src.simulate import simulate_races
from src.app_services.historical_runs import historical_events, replay_config
from src.app_services.simulation_jobs import write_json


def prepare_historical(job, folder):
    selection = job['historical']
    print(f"Loading historical calendar: {selection['year']}…", flush=True)
    events = historical_events(selection['year'], Path.cwd())
    matching = next((e for e in events if e['event'] == selection['event']), None)
    if not matching or selection['session'] not in matching['sessions']:
        raise ValueError('That historical event/session is not in the completed-session calendar.')
    source = folder/'source'
    source.mkdir(exist_ok=True)
    config = replay_config(selection, source, job['n_sims'], job['seed'], job['overtaking_difficulty'])
    # The existing fantasy pipeline updates its price template in-place. Give
    # it a private copy so a past roster cannot overwrite the current season.
    reference = source/'reference'
    reference.mkdir(exist_ok=True)
    prices = Path(config['data']['fantasy_prices_path'])
    local_prices = reference/'fantasy_prices.csv'
    if prices.is_file():
        shutil.copy2(prices, local_prices)
    config['data']['fantasy_prices_path'] = str(local_prices)
    config_path = folder/'historical_config.json'
    write_json(config_path, config)
    print('Preparing historical inputs (downloads are cached). Live forecasts and trained calibration are OFF.', flush=True)
    print('This is a historical replay, not a leakage-free backtest.', flush=True)
    from src.app_services.run_service import run_pipeline_with_config
    # The pipeline temporarily redirects sys.stdout to its callback; retain the
    # original stream to avoid recursively writing back into that callback.
    output_stream = sys.stdout
    code = run_pipeline_with_config(config_path, lambda text: print(text, end='', flush=True, file=output_stream))
    if code:
        raise RuntimeError('Historical input preparation failed. See the pipeline error above.')
    shutil.copy2(source/'driver_model_features.csv', folder/'features.csv')
    strategy = source/'strategy/predicted_tyre_strategy.csv'
    if strategy.is_file():
        shutil.copy2(strategy, folder/'strategies.csv')
    print('Historical inputs ready. Starting the selected simulation.', flush=True)


def run(folder: Path):
    job = json.loads((folder/'job.json').read_text(encoding='utf-8'))
    if job.get('input_source') == 'historical':
        prepare_historical(job, folder)
    print(f"Starting {job['label']} using saved features from {job['source_dir']}", flush=True)
    if job['kind'] == 'monte_carlo':
        print(f"Simulating {job['n_sims']:,} races · seed {job['seed']} · neutral weather modifiers", flush=True)
        summary, positions, _ = simulate_races(pd.read_csv(folder/'features.csv'),
            n_sims=job['n_sims'], seed=job['seed'], overtaking_difficulty=job['overtaking_difficulty'])
        summary.to_csv(folder/'simulation_summary.csv', index=False)
        positions.to_csv(folder/'position_matrix.csv', index=False)
    else:
        if job['kind'] == 'experiments':
            prepare(folder/'features.csv', folder/'strategies.csv', folder)
            inputs = folder/'experiment_inputs.csv'
            if job['scenario'] != 'all':
                cases = pd.read_csv(inputs, keep_default_na=False)
                cases = cases[cases.scenario.isin(['baseline', job['scenario']])]
                cases.to_csv(inputs, index=False)
                print(f"Selected {len(cases)} cases: baseline + {job['scenario']}", flush=True)
                manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
                manifest.update(case_count=len(cases), scenarios=['baseline',job['scenario']], inputs_sha256=sha256(inputs))
                (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        else:
            inputs = export_simulink_inputs(folder/'features.csv', folder/'lap_dynamics_inputs.csv', folder/'strategies.csv')
        quote = lambda path: str(path).replace("'", "''")
        model_dir = Path(__file__).resolve().parents[1]/'matlab'
        command = f"addpath('{quote(model_dir)}'); run_lap_dynamics('{quote(inputs)}','{quote(folder)}',false);"
        print('Starting MATLAB. Initial startup and license checks may take a minute.', flush=True)
        subprocess.run([job['matlab'], '-batch', command], check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if job['kind'] == 'experiments':
            print('Verifying every lap against the independent reference…', flush=True)
            verify(folder)
    print('Simulation complete. Results are ready to review.', flush=True)


if __name__ == '__main__':
    run(Path(sys.argv[1]).resolve())
