import json
import pytest
from src.app_services.automation_health import record, summarize


@pytest.mark.parametrize('result, status, code', [
    ({'post_race':[{'status':'failed'}]}, 'failed', 1),
    ({'deliveries':[{'ok':False,'error':'hidden'}]}, 'failed', 1),
    ({'discord':{'ok':False,'delivery_state':'uncertain','skipped':True}}, 'failed', 1),
    ({'discord':{'ok':False,'delivery_state':'pending','skipped':True}}, 'waiting', 0),
    ({'post_race':[{'status':'waiting_for_results'}]}, 'waiting', 0),
    ({'fantasy_collection':{'status':'error'}}, 'warning', 0),
    ({'ensemble_shadow':{'status':'capture_failed'}}, 'warning', 0),
    ({'classification_checks':{'status':'access_unavailable'}}, 'warning', 0),
    ({'post_race':[{'status':'completed','classification_checks':{'status':'capture_failed'}}]}, 'warning', 0),
    ({'post_race':[{'status':'failed','classification_checks':{'status':'access_unavailable'}}]}, 'failed', 1),
    ({'status':'skipped','reason':'already_completed'}, 'ok', 0),
])
def test_outcomes_distinguish_failures_optional_warnings_and_waits(result,status,code):
    health = summarize(result)
    assert health['status'] == status and health['exit_code'] == code


def test_health_receipt_does_not_copy_errors_or_credentials(tmp_path):
    record(tmp_path, {'deliveries':[{'ok':False,'error':'PRIVATE WEBHOOK VALUE'}]})
    text = (tmp_path/'outputs/automation/last_health.json').read_text()
    assert 'PRIVATE' not in text
    assert json.loads(text)['failures'] == ['deliveries.0']
