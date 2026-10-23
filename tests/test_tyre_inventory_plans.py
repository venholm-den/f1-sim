import numpy as np
import pandas as pd
import pytest

from src.agent_race import _plan_tables
from src.pit_scenarios import assumed_plans, inventory_plans, plan_lap_costs


def inputs(medium=1):
    frame = pd.DataFrame({'Driver': ['AAA']})
    inventory = pd.DataFrame({'Driver': ['AAA', 'AAA'], 'Compound': ['MEDIUM', 'HARD'],
        'estimated_new_sets_remaining': [medium, 1], 'inventory_confidence': ['Medium', 'High']})
    ledger = pd.DataFrame({'Driver': ['AAA', 'AAA', 'AAA'], 'Session': ['FP1', 'FP2', 'Q'],
        'Compound': ['MEDIUM', 'MEDIUM', 'MEDIUM'], 'end_tyre_life': [8, 12, 3]})
    return frame, inventory, ledger


def test_plans_consume_distinct_pool_entries_use_end_age_not_stint_count():
    frame, inventory, ledger = inputs()
    plans = inventory_plans(frame, 20, inventory, ledger)
    two = plans[1]
    assert two['tyre_ages'] == [0, 12, 0]
    assert len(set(two['estimated_set_ids'])) == 3
    assert not two['official_inventory']
    # Three observations do not imply three available used sets.
    plans = inventory_plans(frame, 20, inventory.assign(estimated_new_sets_remaining=[0, 1]), ledger)
    assert len(plans) == 1 and plans[0]['weight'] == 1
    assert plans[0]['tyre_ages'] == [12, 0]


def test_used_ages_apply_to_aggregate_and_agent_tables_consistently():
    plan = assumed_plans(pd.DataFrame({'Driver': ['AAA']}), 20)[0]
    used = {**plan, 'tyre_ages': [4, 6]}
    costs = plan_lap_costs(used, 20)-plan_lap_costs(plan, 20)
    assert costs[:9] == pytest.approx(np.full(9, .05*4))
    assert costs[9:] == pytest.approx(np.full(11, .03*6))
    _, _, ages, _ = _plan_tables([used], 20)
    assert ages[0, 0] == 4 and ages[0, 9] == 6
    with pytest.raises(ValueError, match='initial tyre age'):
        plan_lap_costs({**plan, 'tyre_ages': [0, -1]}, 20)


def test_unknown_inventory_or_unavailable_scenarios_do_not_fabricate_fresh_sets():
    frame, inventory, ledger = inputs()
    with pytest.raises(ValueError, match='frozen tyre inventory'):
        inventory_plans(frame, 20, None, ledger)
    with pytest.raises(ValueError, match='confidence'):
        inventory_plans(frame, 20, inventory.assign(inventory_confidence='Unknown'), ledger)
    with pytest.raises(ValueError, match='No feasible'):
        inventory_plans(frame, 20, inventory.assign(estimated_new_sets_remaining=0), ledger.iloc[:0])
    with pytest.raises(ValueError, match='Target race'):
        inventory_plans(frame, 20, inventory, ledger.assign(Session='R'))
    with pytest.raises(ValueError, match='Duplicate'):
        inventory_plans(frame, 20, pd.concat([inventory, inventory]), ledger)


def test_future_snapshots_freeze_inventory_and_verify_its_hash(tmp_path):
    from src.app_services.beta import freeze_snapshot, verified_snapshot
    frame, inventory, ledger = inputs()
    frame.assign(avg_finish=1.).to_csv(tmp_path/'simulation_summary.csv', index=False)
    inventory.to_csv(tmp_path/'tyre_inventory_estimated.csv', index=False)
    ledger.to_csv(tmp_path/'tyre_set_ledger_estimated.csv', index=False)
    manifest = freeze_snapshot(tmp_path, {'race_start_utc': '2026-12-01T00:00:00Z'}, now='2026-11-01T00:00:00Z')
    assert 'tyre_inventory_estimated.csv' in manifest['files']
    assert 'tyre_set_ledger_estimated.csv' in manifest['files']
    verified_snapshot(tmp_path)
    (tmp_path/'frozen/tyre_inventory_estimated.csv').write_text('altered estimate')
    with pytest.raises(ValueError, match='Frozen snapshot changed'):
        verified_snapshot(tmp_path)
