from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.run_lap_experiments import prepare, reference_laps, verify


def test_reference_includes_initial_age_and_resets_after_pit():
    case = pd.Series(dict(race_laps=5, initial_tyre_age_laps=2, pit_laps='2;4',
        initial_fuel_penalty_seconds=1, fuel_gain_per_lap_seconds=.5,
        pit_loss_seconds=20, base_lap_time_seconds=80, pace_offset_seconds=0,
        tyre_degradation_seconds_per_lap=.1))
    result = reference_laps(case)
    assert result.tyre_age_laps.tolist() == [2,3,0,1,0]
    assert result.fuel_penalty_seconds.tolist() == [1,.5,0,0,0]
    assert result.cumulative_time_seconds.iloc[-1] == pytest.approx(442.1)


def test_batch_is_complete_and_verifier_rejects_tampered_inputs(tmp_path):
    features = tmp_path/'features.csv'
    strategies = tmp_path/'strategies.csv'
    pd.DataFrame({'Driver':['A','B'], 'Team':['T','T'], 'estimated_race_laps':[60,60],
                  'projected_lap_time':[80,81]}).to_csv(features,index=False)
    pd.DataFrame({'Driver':['A','B'], 'expected_stops':[1,2]}).to_csv(strategies,index=False)
    output = tmp_path/'experiments'
    prepare(features,strategies,output)
    inputs = output/'experiment_inputs.csv'
    cases = pd.read_csv(inputs, keep_default_na=False)
    assert len(cases) == 22
    assert cases.case_id.is_unique
    assert set(cases.scenario) == {'baseline','stops_0','stops_1','stops_2','stops_3',
        'pit_early_5','pit_late_5','degradation_low','degradation_high','pit_loss_low','pit_loss_high'}
    assert json.loads((output/'manifest.json').read_text())['case_count'] == 22
    inputs.write_text(inputs.read_text()+'\n')
    with pytest.raises(ValueError,match='changed after preparation'):
        verify(output)
