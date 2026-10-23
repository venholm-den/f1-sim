"""Loopback-only preview of the same desktop UI and Python API."""
from __future__ import annotations

import json
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

METHODS = {'lab_state','lab_start','lab_status','lab_results','lab_cancel','lab_open_folder','lab_export','lab_historical_events',
           'lab_next_race','lab_share_export',
           'initial_state','events_for_year','setup_options','setup_track','outputs','start_run','run_status','open_output_dir',
           'workbench_status','workbench_data','workbench_open_data','workbench_save','workbench_export',
           'workbench_compare','workbench_weather','workbench_history',
           'historical_state','historical_start','historical_preview','historical_export','historical_open',
           'historical_auth_state','historical_auth_start','historical_auth_cancel',
           'replay_sessions','replay_load','replay_lap',
           'training_state','training_start', 'automation_state','automation_load','automation_preferences',
           'fantasy_state','fantasy_refresh','fantasy_open'}


def make_server(api, assets: Path, port=0):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, code, body, content_type='application/json'):
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if (self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}'
                    or self.headers.get('Sec-Fetch-Site') == 'cross-site'):
                self.respond(403,b'{}'); return
            name = urlparse(self.path).path.lstrip('/') or 'index.html'
            if name == 'bridge.js':
                script = "window.f1Api=new Proxy({}, {get:(_,method)=>(...args)=>fetch('/api/'+method,{method:'POST',headers:{'Content-Type':'application/json','X-F1-Token':TOKEN},body:JSON.stringify(args)}).then(async r=>{const b=await r.json();if(!r.ok)throw Error(b.error);return b;})});".replace('TOKEN',json.dumps(token))
                self.respond(200,script.encode(),'text/javascript'); return
            if '/' in name or name not in {'centre.html','centre.css','centre.js','index.html','app.css','workbench.js','historical.js','training.js','fantasy.js','app.js','pc-runs.js','centre-nocturne.css','tyre-strategy.js','tyre-strategy.css','replay.js','replay.css'}:
                self.respond(404,b'{}'); return
            path = assets/name
            types = {'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css'}
            self.respond(200,path.read_bytes(),types[path.suffix])

        def do_POST(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            if (self.headers.get('X-F1-Token') != token
                    or self.headers.get('Host') != origin.removeprefix('http://')
                    or self.headers.get('Origin', origin) != origin):
                self.respond(403,b'{"error":"Invalid session"}'); return
            method = urlparse(self.path).path.removeprefix('/api/')
            if method not in METHODS:
                self.respond(404,b'{"error":"Unknown method"}'); return
            try:
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length < 20000:
                    raise ValueError('Invalid request size.')
                args = json.loads(self.rfile.read(length))
                if not isinstance(args,list):
                    raise ValueError('Arguments must be an array.')
                result = getattr(api,method)(*args)
                self.respond(200,json.dumps(result,allow_nan=False).encode())
            except Exception as exc:
                self.respond(400,json.dumps({'error':str(exc)}).encode())

    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def serve(api, open_browser=True, start_page=''):
    from portable_app.web_main import web_asset
    server = make_server(api, web_asset('centre.html').parent)
    url = f'http://127.0.0.1:{server.server_port}/{start_page}'
    print(f'Race Workbench: {url}',flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        api.lab_cancel()
        server.server_close()
