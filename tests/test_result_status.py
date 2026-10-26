import numpy as np
import pandas as pd
import pytest

from src.result_status import classify_result_status, retirement_label, mechanical_label, retirement_outcome
from types import SimpleNamespace


@pytest.mark.parametrize('status', ['Finished', 'Lapped', '+1 Lap', '+12 Laps', ' + 2 laps '])
def test_lapped_drivers_are_finishers(status):
    assert classify_result_status(status) == 'finished'
    assert retirement_label(status) == 0
    assert mechanical_label(status) == 0


@pytest.mark.parametrize('status', ['Retired', 'Power loss', 'Rear wing'])
def test_retirement_does_not_establish_cause(status):
    assert retirement_label(status) == 1
    assert np.isnan(mechanical_label(status))


@pytest.mark.parametrize('status', ['Did not start', 'Withdrawn', 'Disqualified', '', None, pd.NA,
                                  'Unknown', '123', '+bogus', 'Lap time deleted'])
def test_unknown_or_nonstarter_not_silently_a_retirement_or_finisher(status):
    assert np.isnan(retirement_label(status))
    assert np.isnan(mechanical_label(status))


@pytest.mark.parametrize('status,classified,label', [
    ('Lapped', 'R', 1), ('Wheel nut', 'R', 1), ('Turbo', 'R', 1),
    ('Retired', '19', 1), ('+5 Laps', '15', 0), ('Lapped', 'N', 0),
    ('Mystery', '12', None), ('Disqualified', 'R', None), ('Did not start', 'R', None),
    ('Brakes', 'W', None), ('Illness', 'W', None), ('Finished', 'D', None),
])
def test_retirement_outcomes_respect_classification_and_keep_unknowns(status, classified, label):
    row = SimpleNamespace(Status=status, ClassifiedPosition=classified, Laps=1)
    actual = retirement_outcome(row)
    assert np.isnan(actual) if label is None else actual == label
