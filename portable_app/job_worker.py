"""Child-process entry point for cancellable simulation jobs."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from scripts.run_lap_experiments import prepare, verify, sha256
from src.simulink_export import export_simulink_inputs
from src.simulate import simulate_races


def run(folder: Path):
    job = json.loads((folder/'job.json').read_text(encoding='utf-8'))
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
