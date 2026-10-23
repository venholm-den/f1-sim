import json
import time
from urllib.parse import parse_qs, quote, urlsplit
from unittest.mock import Mock

import jwt
import pytest
import requests

from fastf1.internals import f1auth
from fastf1.internals.f1account import SubscriptionToken, TokenStore, token_manager
from src.app_services import f1_account


@pytest.fixture
def store(tmp_path, monkeypatch):
    local = TokenStore(tmp_path/'auth.json')
    monkeypatch.setattr(TokenStore, 'default', lambda: local)
    return local


def test_local_status_never_returns_token_or_account_claims(store):
    assert f1_account.stored_status()['status'] == 'signed_out'
    store.save(SubscriptionToken('private-token', time.time()+3600))
    status = f1_account.stored_status()
    assert status['status'] == 'signed_in'
    assert 'private-token' not in json.dumps(status)
    store.save(SubscriptionToken('private-token', time.time()-1))
    assert f1_account.stored_status()['status'] == 'expired'


def callback(url, token):
    port = parse_qs(urlsplit(url).query)['port'][0]
    return requests.post(f'http://127.0.0.1:{port}/auth',
                         json={'loginSession': quote(json.dumps({'data': {'subscriptionToken': token}}))},
                         timeout=5)


@pytest.mark.parametrize('code, expected', [(200, 'signed_in'), (401, 'access_denied'), (403, 'access_denied'), (503, 'error')])
def test_browser_callback_verifies_access_before_saving(store, monkeypatch, code, expected, capsys):
    urls = []
    account = f1_account.F1Account(open_browser=urls.append)
    verify = Mock()
    monkeypatch.setattr(f1auth, '_verify_jwt', verify)
    response = Mock(status_code=code)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    probe = Mock(return_value=response)
    monkeypatch.setattr(f1_account.requests, 'get', probe)
    secret = jwt.encode({'exp': time.time()+3600, 'email': 'private@example.invalid'}, 'fake-test-secret-at-least-32-bytes-long', algorithm='HS256')
    assert account.start()['status'] == 'waiting'
    assert callback(urls[0], secret).status_code == 200
    account._thread.join(timeout=5)
    assert not account._thread.is_alive()
    assert account.state()['status'] == expected
    verify.assert_called_once_with(secret)
    assert probe.call_args.kwargs['allow_redirects'] is False
    assert probe.call_args.kwargs['headers']['Authorization'] == 'Bearer '+secret
    assert (store.load() is not None) == (code == 200)
    assert secret not in json.dumps(account.state())+capsys.readouterr().out
    assert 'private@example.invalid' not in json.dumps(account.state())
    # The callback port is closed after success or failure.
    with pytest.raises(requests.ConnectionError):
        callback(urls[0], secret)


def test_invalid_signature_does_not_probe_or_replace_existing_token(store, monkeypatch):
    store.save(SubscriptionToken('previous-token', time.time()+3600))
    monkeypatch.setattr(f1auth, '_verify_jwt', Mock(side_effect=ValueError('secret-details')))
    probe = Mock()
    monkeypatch.setattr(f1_account.requests, 'get', probe)
    urls = []
    account = f1_account.F1Account(open_browser=urls.append)
    account.start()
    callback(urls[0], 'invalid-token')
    account._thread.join(timeout=5)
    assert account.state()['status'] == 'error'
    assert 'secret-details' not in str(account.state())
    assert store.load().value == 'previous-token'
    probe.assert_not_called()


def test_cancel_timeout_and_reopen_close_listener_without_changing_saved_token(store):
    store.save(SubscriptionToken('previous-token', time.time()+3600))
    urls = []
    account = f1_account.F1Account(open_browser=urls.append)
    account.start()
    account.start()
    assert len(urls) == 2 and urls[0] == urls[1]
    assert account.cancel()['status'] == 'cancelled'
    account._thread.join(timeout=3)
    assert not account._thread.is_alive()
    assert store.load().value == 'previous-token'
    timeout = f1_account.F1Account(timeout=0.05, open_browser=urls.append)
    timeout.start()
    timeout._thread.join(timeout=3)
    assert timeout.state()['status'] == 'expired'
    assert store.load().value == 'previous-token'


def test_malformed_callback_can_be_retried(store):
    urls = []
    account = f1_account.F1Account(open_browser=urls.append)
    account.start()
    port = parse_qs(urlsplit(urls[0]).query)['port'][0]
    response = requests.post(f'http://127.0.0.1:{port}/auth', json={'loginSession': 'invalid-json'}, timeout=5)
    assert response.status_code == 400
    assert account.state()['status'] == 'waiting'
    account.cancel()
    account._thread.join(timeout=3)


def test_worker_reuses_token_without_interactive_renewal(store, monkeypatch):
    from fastf1.exceptions import F1AuthError
    monkeypatch.setattr(token_manager, '_store', store)
    monkeypatch.setattr(token_manager, '_token', None)
    monkeypatch.setattr(token_manager, '_authenticate', Mock())
    f1_account.configure_worker_auth()
    with pytest.raises(F1AuthError, match='Historical Data'):
        token_manager.get()
    store.save(SubscriptionToken('existing-token', time.time()+3600))
    assert token_manager.get().value == 'existing-token'
    with pytest.raises(F1AuthError, match='Historical Data'):
        token_manager.get(force_renew=True)
