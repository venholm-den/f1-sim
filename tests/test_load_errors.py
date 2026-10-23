from __future__ import annotations

import json

import pytest
import requests
from fastf1.exceptions import DataNotLoadedError, RateLimitExceededError

from src.app_services import load_errors
from src.app_services.load_errors import session_load_message


def wrapped(cause):
    try:
        try:
            raise cause
        except Exception as exc:
            raise RuntimeError('Race Setup failed. See the pipeline error above.') from exc
    except RuntimeError as outer:
        return outer


@pytest.mark.parametrize('cause, expected', [
    (DataNotLoadedError('The data you are trying to access has not been loaded yet.'), load_errors.NOT_PUBLISHED),
    (ValueError('No laps found for 2026 Monaco Grand Prix Q'), load_errors.NOT_PUBLISHED),
    (RateLimitExceededError('Hard limit hit'), load_errors.RATE_LIMITED),
    (requests.ConnectionError('Max retries exceeded'), load_errors.OFFLINE),
])
def test_fastf1_failures_get_a_plain_message(cause, expected):
    assert session_load_message(wrapped(cause)) == expected


def test_other_errors_are_left_alone():
    assert session_load_message(wrapped(KeyError('grid_position'))) is None


def test_worker_records_plain_failure_for_the_app(tmp_path, monkeypatch, capsys):
    from portable_app import job_worker

    def failing(folder):
        raise wrapped(DataNotLoadedError('not loaded'))

    monkeypatch.setattr(job_worker, '_run', failing)
    with pytest.raises(RuntimeError):
        job_worker.run(tmp_path)
    failure = json.loads((tmp_path/'failure.json').read_text(encoding='utf-8'))
    assert failure == {'message': load_errors.NOT_PUBLISHED, 'session_load': True}
    assert load_errors.NOT_PUBLISHED in capsys.readouterr().out


def test_pipeline_keeps_its_real_cause(monkeypatch):
    import main as pipeline_main
    from src.app_services import run_service

    def boom():
        raise DataNotLoadedError('not loaded')

    monkeypatch.setattr(pipeline_main, 'main', boom)
    assert run_service.run_pipeline_with_config('config.json', lambda _: None) == 1
    assert isinstance(run_service.last_failure, DataNotLoadedError)
