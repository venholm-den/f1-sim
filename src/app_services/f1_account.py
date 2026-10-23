"""Desktop adapter for the browser sign-in in pinned FastF1 3.9.0a0.

Only the upstream token store receives credentials. UI responses and job logs
contain status text, never the subscription token or its decoded claims.
"""
from __future__ import annotations

import threading
import time
import webbrowser
from datetime import datetime, timezone

import requests

PROBE_URL = ('https://livetiming.formula1.com/static/2025/'
             '2025-04-20_Saudi_Arabian_Grand_Prix/'
             '2025-04-18_Practice_1/WeatherData.jsonStream')


def stored_status():
    from fastf1.internals.f1account import TokenStore
    token = TokenStore.default().load()
    if token is None:
        return {'status': 'signed_out', 'message': 'Sign in with an active F1 TV Access subscription or higher.'}
    if not token.is_valid():
        return {'status': 'expired', 'message': 'Your F1 sign-in has expired. Sign in again before downloading.'}
    return {'status': 'signed_in', 'message': 'F1 sign-in saved on this PC.',
            'expires_at': datetime.fromtimestamp(token.expires_at, timezone.utc).isoformat()}


def configure_worker_auth():
    """Workers reuse saved tokens, but never wait for a browser or console."""
    from fastf1.exceptions import F1AuthError
    from fastf1.internals.f1account import token_manager

    def sign_in_required():
        raise F1AuthError('Sign in to F1 from Historical Data before resuming the download.')

    # FastF1 has no public non-interactive switch. Keep this pinned-version
    # integration here; existing adapters reference this same manager.
    token_manager._authenticate = sign_in_required


class F1Account:
    def __init__(self, *, timeout=300, open_browser=webbrowser.open):
        self.timeout = timeout
        self.open_browser = open_browser
        self._lock = threading.RLock()
        self._thread = None
        self._cancel = threading.Event()
        self._result = None
        self._url = None

    def state(self):
        with self._lock:
            if self._result is not None:
                if self._result['status'] == 'signed_in':
                    status = stored_status()
                    return self._result.copy() if status['status'] == 'signed_in' else status
                return dict(self._result)
            return stored_status()

    def start(self):
        from fastf1.internals.f1auth import _AuthHandler, _AuthServer, LOGIN_URL

        # Reuse FastF1's cookie extraction and signed-token verification. Bound
        # the callback size and silence HTTP logs, including malformed callbacks.
        class Handler(_AuthHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 65536:
                        raise ValueError('Invalid callback size')
                    super().do_POST()
                except (ValueError, TypeError, KeyError, AttributeError):
                    self.send_error(400, 'Invalid sign-in callback')

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                # Let the user reopen the same browser step without creating
                # a second callback listener or overwriting a completed login.
                if self._url:
                    self.open_browser(self._url)
                return self.state()
            class Server(_AuthServer):
                def get_request(self):
                    connection, address = super().get_request()
                    connection.settimeout(5)
                    return connection, address

            server = Server()
            server.RequestHandlerClass = Handler
            server.timeout = 0.5
            self._cancel.clear()
            self._url = f'{LOGIN_URL}?port={server.server_port}'
            self._result = {'status': 'waiting', 'message':
                'Finish signing in in your browser. Install the FastF1 Companion extension if prompted. This step expires in five minutes.'}
            self._thread = threading.Thread(target=self._finish, args=(server,), daemon=True)
            self._thread.start()
            try:
                self.open_browser(self._url)
            except Exception:
                self._cancel.set()
                self._result = {'status': 'error', 'message': 'The browser could not be opened. Try signing in again.'}
            return self.state()

    def cancel(self):
        with self._lock:
            self._cancel.set()
            self._result = {'status': 'cancelled', 'message': 'Sign-in cancelled. Previously saved sign-in is unchanged.'}
            return self.state()

    def _finish(self, server):
        from fastf1.internals.f1auth import _verify_jwt
        from fastf1.internals.f1account import SubscriptionToken, TokenStore

        result = {'status': 'error', 'message': 'F1 sign-in could not be completed. Please try again.'}
        try:
            deadline = time.monotonic() + self.timeout
            with server:
                while not server.received.is_set() and not self._cancel.is_set() and time.monotonic() < deadline:
                    server.handle_request()
            if self._cancel.is_set():
                return
            if not server.received.is_set():
                result = {'status': 'expired', 'message': 'The browser sign-in timed out. Sign in again to retry.'}
            elif server.token:
                _verify_jwt(server.token)
                token = SubscriptionToken.from_jwt(server.token)
                if not token.is_valid():
                    raise ValueError('Expired token')
                with requests.get(PROBE_URL, headers={'Authorization': token.authorization_header},
                                  timeout=(5, 20), allow_redirects=False) as response:
                    code = response.status_code
                if code == 200:
                    with self._lock:
                        if self._cancel.is_set():
                            return
                        TokenStore.default().save(token)
                    result = {**stored_status(), 'message': 'Signed in. Historical timing access verified. Resume your download.'}
                elif code in (401, 403):
                    result = {'status': 'access_denied', 'message':
                        'F1 refused archive access. Check that F1 TV Access or a higher subscription is active, then sign in again.'}
                else:
                    result = {'status': 'error', 'message': f'F1 archive check returned HTTP {code}. Try signing in again later.'}
        except Exception:
            # Upstream exceptions can include response/credential details.
            # Keep them out of both the browser bridge and durable job logs.
            pass
        finally:
            server.token = None
            with self._lock:
                self._url = None
                if not self._cancel.is_set():
                    self._result = result
