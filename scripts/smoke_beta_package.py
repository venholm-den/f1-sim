"""Exercise a built EXE from a fresh data workspace; never alter saved runs.

Usage: python -m scripts.smoke_beta_package path/to/app.exe
Downloads public race data. This is a packaging check, not an accuracy test.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from uuid import uuid4

import pandas as pd

from src.app_services.app_paths import initialize_user_workspace
from src.app_services.beta import dump_new, verified_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    args = parser.parse_args()
    executable = args.executable.resolve(strict=True)
    root = initialize_user_workspace(Path('outputs/beta_acceptance').resolve()/uuid4().hex[:12])
    folder = root/'forecast'
    folder.mkdir()
    job = {'kind':'forecast', 'n_sims':100, 'seed':42, 'overtaking_difficulty':.55}
    dump_new(folder/'job.json', job)
    start = time.monotonic()
    print(f'Clean data workspace: {root}', flush=True)
    worker = subprocess.Popen([str(executable),'--job-worker',str(folder)], cwd=root)
    try:
        code = worker.wait(timeout=900)
    except subprocess.TimeoutExpired:
        worker.kill()
        worker.wait()
        raise RuntimeError(f'Packaged forecast timed out. See {folder / "run.log"}')
    if code:
        raise RuntimeError(f'Packaged forecast failed ({code}). See {folder / "run.log"}')
    manifest = verified_snapshot(folder)
    rows = pd.read_csv(folder/'simulation_summary.csv')
    assert len(rows) >= 20
    assert abs(rows.win_chance.sum()-1) < .00001
    assert manifest['category'] == 'prospective'
    # Exercise the packaged Discord worker against loopback only, never Discord.
    attachments = []

    class LocalWebhook(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            message = BytesParser(policy=default).parsebytes(
                f"Content-Type: {self.headers['Content-Type']}\r\n\r\n".encode() + body)
            files = [part.get_filename() for part in message.iter_parts() if part.get_filename()]
            attachments.append(files)
            self.send_response(204)
            self.end_headers()

    server = ThreadingHTTPServer(('127.0.0.1', 0), LocalWebhook)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    (root / '.env.discord').write_text(
        f'DISCORD_WEBHOOK_URL=http://127.0.0.1:{server.server_port}/test\n', encoding='utf-8')
    upload = root / 'discord_test'
    upload.mkdir()
    dump_new(upload / 'job.json', {'kind': 'discord', 'forecast_folder': str(folder)})
    try:
        subprocess.run([str(executable), '--job-worker', str(upload)], cwd=root,
                       timeout=60, check=True)
        count = len(attachments)
        subprocess.run([str(executable), '--job-worker', str(upload)], cwd=root,
                       timeout=60, check=True)
        assert len(attachments) == count, 'Duplicate delivery was not prevented.'
        assert all(0 < len(batch) <= 10 for batch in attachments)
        plan = json.loads((folder/'discord_report/delivery_plan.json').read_text(encoding='utf-8'))
        delivered = [name for batch in attachments for name in batch]
        assert delivered == [Path(name).name for name in plan['files']]
        assert {'simulation_summary.csv', 'race_outlook.png'}.issubset(delivered)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    # An early evaluation must exit nonzero, not open a blocking GUI dialog.
    rejected = root/'early_score'
    rejected.mkdir()
    dump_new(rejected/'job.json', {'kind':'score','forecast_folder':str(folder)})
    rejected_worker = subprocess.Popen([str(executable),'--job-worker',str(rejected)],cwd=root)
    try:
        reject_code = rejected_worker.wait(timeout=60)
    except subprocess.TimeoutExpired:
        rejected_worker.kill()
        rejected_worker.wait()
        raise RuntimeError('Early scoring did not exit cleanly.')
    assert reject_code != 0
    assert 'Scoring opens eight hours' in (rejected/'run.log').read_text(encoding='utf-8')
    result = {'passed':True,'executable':str(executable),'drivers':len(rows),
              'elapsed_seconds':round(time.monotonic()-start,2), 'context':manifest['context'],
              'early_scoring_rejected':True,'clean_machine_test':False,
              'discord_loopback_test':True, 'discord_duplicate_prevented':True,
              'discord_attachments':attachments}
    dump_new(root/'acceptance.json',result)
    print(json.dumps(result,indent=2),flush=True)


if __name__ == '__main__':
    main()
