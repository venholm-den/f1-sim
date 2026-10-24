import numpy as np
import pandas as pd
import pytest
import json
from types import SimpleNamespace

from src.form_adjustment import (apply_form,apply_retirement_prior,fit_form,form_inputs,
                                 training_table,validate_packet,packet_from_races)
from src.simulate import simulate_races
from tests.test_simulate import _minimal_features


def packet():
    return pd.DataFrame([dict(Year=2025,Round=r,Driver=f'D{i}',Team=f'T{i//2}',FieldSize=10,
        Position=i+1,QPosition=i+1,PacePct=i*.1,Status='Finished') for r in range(1,11) for i in range(10)])


def features():
    base=_minimal_features().iloc[[0]*10].reset_index(drop=True)
    base['Driver']=[f'D{i}' for i in range(10)];base['Team']=[f'T{i//2}' for i in range(10)]
    base['grid_position']=np.arange(1,11);base['race_pace_score']=np.arange(10)*.1
    base['long_run_pace_score']=base.race_pace_score+.2
    return base


def test_future_and_target_outcomes_never_affect_fit_or_form_inputs():
    history=packet();roster=features();cutoff=(2025,9)
    old=fit_form(training_table(history),cutoff,'Q')
    changed=history.copy();mask=changed.Round.ge(9)
    changed.loc[mask,'Position']=11-changed.loc[mask,'Position']
    changed.loc[mask,'Status']='Engine';changed.loc[mask,'PacePct']=999.
    new=fit_form(training_table(changed),cutoff,'Q')
    assert old==new
    pd.testing.assert_frame_equal(form_inputs(history,roster,cutoff),form_inputs(changed,roster,cutoff))


def test_q_requires_real_qualifying_order_and_preserves_grid_facts():
    history=packet();base=features();model=fit_form(training_table(history),(2025,9),'Q')
    with pytest.raises(ValueError,match='official qualifying'):
        apply_form(base,history,model,(2025,9),'Q')
    q=dict(zip(base.Driver,range(1,11)))
    base['grid_position']=np.arange(10,0,-1)  # Later penalties must not replace the Q anchor.
    output=apply_form(base,history,model,(2025,9),'Q',q_positions=q)
    pd.testing.assert_series_equal(output.grid_position,base.grid_position)
    np.testing.assert_allclose(output.long_run_pace_score-output.race_pace_score,.2)


def test_zero_weight_is_exact_legacy_and_inputs_are_not_mutated():
    history=packet();base=features();original=base.copy(deep=True)
    model=fit_form(training_table(history),(2025,9),'PRE')
    output=apply_form(base,history,model,(2025,9),'PRE',weight=0)
    pd.testing.assert_frame_equal(output,base)
    a,_,_=simulate_races(base,n_sims=100,seed=42)
    b,_,_=simulate_races(output,n_sims=100,seed=42)
    pd.testing.assert_frame_equal(a,b)
    apply_form(base,history,model,(2025,9),'PRE')
    pd.testing.assert_frame_equal(base,original)


def test_retirement_unknowns_are_not_healthy_and_generic_retired_is_known():
    history=packet();base=features()
    history.loc[history.Driver.eq('D0'),'Status']='Unspecified'
    history.loc[history.Driver.eq('D1'),'Status']='Retired'
    output=apply_retirement_prior(base,history,(2025,3))
    assert output.loc[0,'retirement_prior_driver_known']==0
    assert output.loc[0,'retirement_prior_team_known']==2
    assert output.loc[0,'retirement_prior_raw']==pytest.approx(.5*(.1+3/12))
    reset=apply_retirement_prior(base,history,(2026,1))
    np.testing.assert_allclose(reset.reliability_score,.1)


def test_insufficient_history_is_explicit_and_invalid_packets_are_rejected():
    history=packet()
    model=fit_form(training_table(history),(2025,3),'PRE')
    assert model['status']=='insufficient_history'
    pd.testing.assert_frame_equal(apply_form(features(),history,model,(2025,3),'PRE'),features())
    with pytest.raises(ValueError,match='unique'):
        validate_packet(pd.concat([history,history.iloc[[0]]]))
    history.loc[0,'QPosition']=np.nan
    with pytest.raises(ValueError,match='permutation'):
        validate_packet(history)


def test_artifact_json_roundtrip_and_early_stages_do_not_read_target_q_or_grid():
    history=packet();base=features();cutoff=(2025,9)
    model=json.loads(json.dumps(fit_form(training_table(history),cutoff,'PRE')))
    first=apply_form(base,history,model,cutoff,'PRE')
    changed=base.copy();changed['grid_position']=np.arange(10,0,-1);changed['q_rank']=999
    second=apply_form(changed,history,model,cutoff,'PRE')
    pd.testing.assert_series_equal(first.race_pace_score,second.race_pace_score)
    for invalid in (np.nan,-.1,.5):
        with pytest.raises(ValueError,match='weight'):
            apply_form(base,history,model,cutoff,'PRE',weight=invalid)


def test_adjusted_pace_still_produces_coherent_simulated_probability_fields():
    history=packet();base=features();model=fit_form(training_table(history),(2025,9),'PRE')
    adjusted=apply_form(base,history,model,(2025,9),'PRE')
    summary,matrix,_=simulate_races(adjusted,n_sims=300,seed=42)
    assert summary.win_chance.sum()==pytest.approx(1)
    assert summary.podium_chance.sum()==pytest.approx(3)
    assert summary.points_chance.sum()==pytest.approx(10)
    np.testing.assert_allclose(matrix[[f'P{i}' for i in range(1,11)]].sum(axis=1),1)


def test_packet_builder_excludes_bad_classifications_instead_of_imputing():
    results=pd.DataFrame({'Abbreviation':['A','B'],'TeamName':['T','T'],
        'Position':[1,1],'Status':['Finished','Finished']})
    race=SimpleNamespace(year=2025,round=1,key=(2025,1),event='Example',
                         sessions={'R':SimpleNamespace(results=results,laps=pd.DataFrame())})
    history=packet_from_races([race])
    assert history.empty
    assert history.attrs['excluded_races'][0]['round']==1
