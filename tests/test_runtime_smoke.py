"""Actual source worker smoke check: offline, disposable workspace, no uploads."""
import time
import pandas as pd
from src.app_services.simulation_jobs import SimulationJobs


def test_source_worker_runs_in_separate_workspace(tmp_path):
    jobs = SimulationJobs(tmp_path)
    pd.DataFrame({'Driver':['A','B'], 'Team':['T','U']}).to_csv(
        tmp_path/'outputs/driver_model_features.csv', index=False)
    launched = jobs.start({'kind':'monte_carlo','n_sims':100})
    try:
        assert jobs.process.wait(timeout=30) == 0
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            result = jobs.status(launched['id'])
            if result['status'] != 'running':
                break
            time.sleep(.02)
        assert result['status'] == 'completed', result['log']
        summary = pd.read_csv(jobs._folder(launched['id'])/'simulation_summary.csv')
        assert set(summary.Driver) == {'A','B'}
        assert {'top10_chance','points_scoring_chance'}.issubset(summary)
        assert 'Simulation complete' in result['log']
    finally:
        if jobs.process.poll() is None:
            jobs.cancel()
