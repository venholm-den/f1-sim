import json
import threading
import urllib.error
import urllib.request
from unittest.mock import Mock

import pytest

from portable_app.centre_server import make_server


def test_loopback_bridge_requires_session_and_same_origin(tmp_path):
    (tmp_path/'index.html').write_text('<title>Test centre</title>')
    (tmp_path/'tyre-strategy.js').write_text('window.TyreStrategy = {};')
    (tmp_path/'tyre-strategy.css').write_text('.tyre-board { color: white; }')
    (tmp_path/'logo.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    api = Mock()
    api.lab_state.return_value = {'features': True}
    server = make_server(api, tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'

    def request(path, headers=None, data=None):
        return urllib.request.urlopen(urllib.request.Request(base+path, headers=headers or {}, data=data))

    try:
        with request('/') as response:
            assert 'Test centre' in response.read().decode()
            assert response.headers['Cross-Origin-Resource-Policy'] == 'same-origin'
        for asset, content_type in [('tyre-strategy.js', 'text/javascript'), ('tyre-strategy.css', 'text/css'), ('logo.svg', 'image/svg+xml')]:
            with request('/'+asset) as response:
                assert response.headers['Content-Type'] == content_type
                assert response.read()
        with request('/bridge.js', {'Sec-Fetch-Site':'same-origin'}) as response:
            script = response.read().decode()
        token = script.split("'X-F1-Token':", 1)[1].split('}', 1)[0].strip('"')
        headers = {'X-F1-Token': token, 'Origin':base}
        with request('/api/lab_state', headers, b'[]') as response:
            assert json.load(response) == {'features':True}
        api.lab_state.assert_called_once_with()
        for path, test_headers, data in [
            ('/bridge.js', {'Sec-Fetch-Site':'cross-site'}, None),
            ('/bridge.js', {'Sec-Fetch-Site':'same-site'}, None),
            ('/', {'Host':'evil.example'}, None),
            ('/api/lab_start', {}, b'[]'),
            ('/api/lab_start', {**headers, 'Origin':'https://evil.example'}, b'[]'),
        ]:
            with pytest.raises(urllib.error.HTTPError) as error:
                request(path, test_headers, data)
            assert error.value.code == 403
        api.lab_start.assert_not_called()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
