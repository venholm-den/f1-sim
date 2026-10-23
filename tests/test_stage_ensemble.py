import copy
import json

import numpy as np
import pandas as pd
import pytest

from src.stage_ensemble import (COMPONENTS, FORECAST_COLUMNS, Episode, ranking_forecast,
    build_components, fit_weights, fit_calibration, blend, validate_forecast)
from src.stage_ensemble_benchmark import load_episodes, run_walk_forward, benchmark


def inputs():
    drivers = [f'D{i:02}' for i in range(12)]
    base = ranking_forecast(np.arange(12),np.full(12,.1),n_sims=300)
    frame = pd.DataFrame(base,columns=FORECAST_COLUMNS)
    frame['Driver'] = drivers
    frame['grid_position'] = range(1,13)
    frame['grid_source'] = 'actual_session_results'
    frame['dnf_chance'] = .1
    results = pd.DataFrame([{'Year':2026,'Round':r,'DriverCode':driver,'Position':i+1}
                           for r in range(1,10) for i,driver in enumerate(drivers)])
    practice = pd.DataFrame({'Year':2026,'Round':8,'DriverCode':drivers,
        'fp2_long_run_relative_pace':np.arange(12)[::-1], 'fp2_long_run_confidence':.65})
    return frame,results,practice


def episodes():
    frame,results,practice = inputs()
    output = []
    for rnd in range(1,10):
        drivers,c,dnf,available = build_components(frame,(2026,rnd),'Q',results,practice,n_sims=300)
        output.append(Episode((2026,rnd),'Q','Test',drivers,c,np.arange(1,13),dnf,
                              np.zeros(12),available))
    return output


def test_blend_preserves_field_totals_and_nested_events():
    e = episodes()[-1]
    prediction = blend(e.components,[.2,.3,.1,.4],.2)
    np.testing.assert_allclose(prediction.sum(axis=0),[78,1,3,10])
    assert np.all(np.diff(prediction[:,1:],axis=1) >= 0)
    with pytest.raises(ValueError,match='nonnegative'):
        blend(e.components,[1.1,-.1,0,0])
    broken = prediction.copy(); broken[0,1] += .1
    with pytest.raises(ValueError):
        validate_forecast(broken)


def test_pre_and_fp2_cannot_use_qualifying_and_pre_cannot_use_practice():
    frame,results,practice = inputs()
    for stage in ('PRE','FP2'):
        _,c,_,available = build_components(frame,(2026,8),stage,results,practice,n_sims=300)
        assert not available['qualifying']['available']
        np.testing.assert_array_equal(c[0],c[1])
        if stage == 'PRE':
            assert not available['practice']['available']
            np.testing.assert_array_equal(c[0],c[3])


def test_target_and_future_results_cannot_change_predictors():
    frame,results,practice = inputs()
    _,before,_,availability = build_components(frame,(2026,8),'Q',results,practice,n_sims=300)
    results.loc[results.Round.ge(8),'Position'] = 999
    frame['actual_position'] = 999
    _,after,_,_ = build_components(frame,(2026,8),'Q',results,practice,n_sims=300)
    np.testing.assert_array_equal(before,after)
    assert availability['recent_form']['source_races'] == [[2026,r] for r in range(3,8)]


def test_sparse_or_stale_components_fall_back_without_fabricated_evidence():
    frame,results,practice = inputs()
    _,c,_,available = build_components(frame,(2026,15),'Q',results,practice.iloc[:2],n_sims=300)
    assert not available['recent_form']['available']
    assert not available['practice']['available']
    np.testing.assert_array_equal(c[0],c[2])
    np.testing.assert_array_equal(c[0],c[3])
    frame['grid_position'] = np.arange(12)+1.1
    _,_,_,available = build_components(frame,(2026,8),'Q',results,practice,n_sims=300)
    assert not available['qualifying']['available']


def test_partial_q_grid_reports_observed_coverage_but_requires_complete_classification():
    frame,results,practice = inputs()
    frame.loc[0,'grid_source'] = 'estimated_model_grid'
    _,c,_,available = build_components(frame,(2026,8),'Q',results,practice,n_sims=300)
    assert available['qualifying']['coverage'] == 11/12
    assert not available['qualifying']['available']
    np.testing.assert_array_equal(c[0],c[1])


def test_weights_only_learn_from_earlier_independent_races():
    data = episodes()
    before,metadata = fit_weights(data,'Q',(2026,8))
    changed = copy.deepcopy(data)
    for row in changed:
        if row.key >= (2026,8):
            row.actual = row.actual[::-1]
    after,_ = fit_weights(changed,'Q',(2026,8))
    np.testing.assert_array_equal(before,after)
    assert metadata['train_races'] == [[2026,r] for r in range(1,8)]
    assert metadata['weights']['practice'] == 0  # Only one usable practice race.
    assert metadata['status'] == 'fitted'
    with pytest.raises(ValueError,match='independent'):
        fit_weights(data+[data[0]],'Q',(2026,8))
    weights,fit = fit_weights(data,'Q',(2026,5))
    np.testing.assert_array_equal(weights,[1,0,0,0])
    assert fit['status'] == 'insufficient_history'


def test_calibration_has_separate_out_of_sample_history():
    data = episodes()
    _,_,fits,stages = run_walk_forward(data)
    assert fits[6]['train_races'] == [[2026,r] for r in range(1,7)]
    assert fits[6]['calibration']['calibration_races'] == []
    assert fits[7]['calibration']['calibration_races'] == [[2026,7]]
    assert stages['Q']['calibration']['uniform_mass'] == 0
    history = [{'key':(2026,r),'stage':'Q','prediction':data[0].components[0],
                'actual':data[0].actual} for r in range(1,9)]
    a,meta = fit_calibration(history,'Q',(2026,7))
    history[-1]['actual'] = data[0].actual[::-1]
    b,_ = fit_calibration(history,'Q',(2026,7))
    assert a == b and len(meta['calibration_races']) == 6
    with pytest.raises(ValueError,match='independent'):
        fit_calibration(history+[history[0]],'Q',(2026,7))


def test_repeated_seeds_count_once_and_inconsistent_driver_coverage_rejected():
    frame,results,practice = inputs()
    frames = []
    for seed in (42,123):
        part = frame.copy()
        part['actual_position'] = np.arange(1,13)
        part['actual_dnf'] = 0
        part['year'],part['round'],part['session'] = 2026,8,'Q'
        part['event'],part['variant'],part['seed'] = 'Test','legacy',seed
        frames.append(part)
    predictions = pd.concat(frames,ignore_index=True)
    assert len(load_episodes(predictions,results,practice,n_sims=300)) == 1
    with pytest.raises(ValueError,match='coverage differs'):
        load_episodes(predictions.iloc[:-1],results,practice,n_sims=300)
    with pytest.raises(ValueError,match='Duplicate'):
        load_episodes(pd.concat([predictions,predictions.iloc[:1]]),results,practice,n_sims=300)


def test_benchmark_refuses_changed_predictions_before_creating_output(tmp_path):
    (tmp_path/'predictions.csv').write_text('changed')
    source = tmp_path/'report.json'
    source.write_text(json.dumps({'artifact_sha256':{'predictions.csv':'wrong'}}))
    with pytest.raises(ValueError,match='checksum'):
        benchmark(source,tmp_path,tmp_path/'output',n_sims=300)
    assert not (tmp_path/'output').exists()
