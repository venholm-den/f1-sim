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
    from src.app_services.f1_account import configure_worker_auth
    configure_worker_auth()
    job = json.loads((folder/'job.json').read_text(encoding='utf-8'))
    if job['kind'] == 'manual_run':
        from datetime import datetime, timezone
        import time
        from src.app_services.run_service import run_pipeline_with_config
        config_path = folder/'manual_config.json'
        config = json.loads(config_path.read_text(encoding='utf-8'))
        output_stream = sys.stdout
        started = time.monotonic()
        code = run_pipeline_with_config(config_path,
            lambda text: print(text, end='', file=output_stream, flush=True))
        if code:
            raise RuntimeError('Race Setup failed. See the pipeline error above.')
        output = Path(config['outputs']['output_dir'])
        write_json(output/'ui_run.json', {'settings': config['run'],
            'completed_at_utc': datetime.now(timezone.utc).isoformat(),
            'elapsed_seconds': round(time.monotonic()-started, 2), 'post_to_discord': False})
        return
    if job['kind'] == 'historical_training':
        from src.app_services.model_training import train
        train(Path.cwd(), folder, json.loads((folder/'training_selection.json').read_text(encoding='utf-8')))
        return
    if job['kind'] == 'historical_download':
        from src.app_services.historical_library import download
        result = download(Path.cwd(), folder, job['archive'])
        print(f"Historical download {result['status']}: {result['downloaded']} saved, {result['skipped']} already stored, {result['failed']} unavailable.", flush=True)
        return
    if job['kind'] == 'discord':
        from src.app_services.discord_settings import local_webhook
        from src.app_services.forecast_automation import post_frozen_forecast
        webhook = local_webhook(Path.cwd())
        if not webhook:
            raise ValueError('Discord webhook is not configured locally.')
        result = post_frozen_forecast(Path(job['forecast_folder']), webhook_url=webhook)
        write_json(folder/'upload_result.json', result)
        if not result.get('ok'):
            raise RuntimeError('Discord delivery requires review or is waiting for its retry delay. No duplicate was sent.')
        print('Discord report already delivered; duplicate skipped.' if result.get('skipped')
              else f"Discord upload complete: {len(result.get('posted_files', []))} attachments.", flush=True)
        return
    if job['kind'] in ('forecast','score'):
        from src.app_services.beta import run_forecast, run_scoring
        if job['kind'] == 'forecast':
            run_forecast(folder, job)
        else:
            run_scoring(folder, Path(job['forecast_folder']))
        print('Simulation complete. Results are ready to review.', flush=True)
        return
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
