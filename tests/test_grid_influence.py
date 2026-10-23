import pandas as pd
import pytest

from src.grid_influence import MAPPINGS, mapped_difficulty, select_mapping
from src.venues import resolve_venue


def observation(year, round, layout, changes, exposure):
    return {'year': year, 'round': round, 'layout_id': layout,
            'order_change_proxy': {'changes': changes, 'exposure': exposure}}


def test_mapping_uses_strictly_earlier_layout_counts_and_falls_back_when_sparse():
    context = {'year': 2026, 'round': 3, 'venue': {'layout_id': 'a'}}
    history = [observation(2025, 1, 'a', 10, 1000), observation(2025, 2, 'a', 10, 1000),
               observation(2025, 3, 'b', 100, 1000)]
    result, evidence = mapped_difficulty('earlier_order_proxy', .7, context, history)
    changed = history + [observation(2026, 3, 'a', 900, 1000), observation(2027, 1, 'a', 900, 1000)]
    assert mapped_difficulty('earlier_order_proxy', .7, context, changed)[0] == result
    assert evidence['prior_layout_races'] == 2 and .25 <= result <= .9
    context['venue']['layout_id'] = 'new'
    assert mapped_difficulty('earlier_order_proxy', .7, context, history)[0] == .7


def test_selection_averages_races_and_ignores_later_scores():
    rows = []
    for stage in ('PRE', 'FP2', 'Q'):
        for mapping in MAPPINGS:
            for r in (1, 2):
                rows.append(dict(session=stage, mapping=mapping, year=2024, round=r,
                    split='development', loss=1 if mapping == 'uniform_055' else 2))
            rows.append(dict(session=stage, mapping=mapping, year=2025, round=1,
                split='previously_seen_diagnostic', loss=100 if mapping == 'uniform_055' else 0))
    frame = pd.DataFrame(rows)
    assert {stage: select_mapping(frame, stage) for stage in ('PRE', 'FP2', 'Q')} == {
        'PRE': 'uniform_055', 'FP2': 'uniform_055', 'Q': 'uniform_055'}
    with pytest.raises(ValueError, match='every declared mapping'):
        select_mapping(frame[frame.mapping != 'active_profile'], 'Q')


@pytest.mark.parametrize('year,event,location,circuit', [
    (2021, 'Portuguese Grand Prix', 'Portimão', 'portimao'),
    (2021, 'French Grand Prix', 'Le Castellet', 'ricard'),
    (2022, 'French Grand Prix', 'Le Castellet', 'ricard'),
    (2021, 'Russian Grand Prix', 'Sochi', 'sochi'),
    (2021, 'Turkish Grand Prix', 'Istanbul', 'istanbul'),
    (2025, 'Abu Dhabi Grand Prix', 'Yas Island', 'yas_marina'),
])
def test_archive_locations_resolve_without_discarding_conflicting_hints(year, event, location, circuit):
    assert resolve_venue(year, event, location=location)['circuit_id'] == circuit
    assert resolve_venue(year, event, location=location, circuit_hint='Monza')['venue_status'] == 'conflict'


def test_melbourne_redesign_is_explicit():
    assert resolve_venue(2021, 'Australian Grand Prix')['layout_id'] == 'albert_park_pre_2022'
    assert resolve_venue(2022, 'Australian Grand Prix')['layout_id'] == 'albert_park_since_2022'


@pytest.mark.parametrize('year,event', [(2008, 'French Grand Prix'), (1995, 'Portuguese Grand Prix'),
                                      (1913, 'Russian Grand Prix')])
def test_historical_event_name_does_not_assign_a_later_venue(year, event):
    assert resolve_venue(year, event)['circuit_id'] is None
