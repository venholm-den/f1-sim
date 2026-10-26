"""Local simulation jobs: isolated processes, durable history and bounded previews."""
from __future__ import annotations

import json
import hashlib
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd
from src.app_services.historical_runs import validate_selection

SCENARIOS = ['all', 'stops_0', 'stops_1', 'stops_2', 'stops_3', 'pit_early_5',
             'pit_late_5', 'degradation_low', 'degradation_high', 'pit_loss_low', 'pit_loss_high']
KINDS = {'monte_carlo': 'Monte Carlo', 'lap_dynamics': 'Lap dynamics', 'experiments': 'Scenario experiments',
         'forecast':'Next race forecast', 'score':'Post-race evaluation', 'discord':'Discord report upload',
         'historical_download': 'Historical data download', 'historical_training': 'Historical model training',
         'archive_replay': 'Archive replay'}


def records(frame):
    return json.loads(frame.to_json(orient='records'))


def write_json(path, value):
    # A unique temp name keeps concurrent writers apart. Windows refuses the
    # replace while a poller has the target open, so retry briefly.
    path = Path(path)
    temporary = path.with_name(f'{path.name}.{uuid4().hex}.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(0.05)


def matlab_executable():
    executable = shutil.which('matlab')
    if executable:
        return executable
    candidates = sorted(Path('C:/Program Files/MATLAB').glob('R*/bin/matlab.exe'), reverse=True)
    return str(candidates[0]) if candidates else None


class SimulationJobs:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.run_root = self.root/'outputs'/'app_runs'
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.process = None
        self.active_id = None
        # Preserve malformed records and surface them instead of blocking startup.
        for path in self.run_root.glob('*/job.json'):
            data = self._read_job(path)
            if data['status'] in ('running', 'cancelling'):
                data['status'] = 'interrupted'
                write_json(path, data)

    def _read_job(self, path):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not all(key in data for key in ('id', 'status', 'created_at')):
                raise ValueError('Job metadata is incomplete.')
            if (not all(isinstance(data[key], str) for key in ('id', 'status', 'created_at'))
                    or data['id'] != path.parent.name):
                raise ValueError('Job identifier differs from its folder.')
            return data
        except (OSError, ValueError, TypeError):
            return {'id': path.parent.name, 'status': 'unreadable', 'created_at': '',
                    'label': 'Unreadable run record', 'metadata_error':
                    'Saved job metadata could not be read. Original files have been preserved.'}

    def _source(self, value):
        path = (self.root / str(value or 'outputs')).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('Choose an output folder inside this project.')
        return path

    def state(self, source_dir='outputs'):
        source = self._source(source_dir)
        features = source/'driver_model_features.csv'
        strategies = source/'strategy'/'predicted_tyre_strategy.csv'
        context = {'label': 'Existing feature snapshot', 'drivers': 0, 'modified': None}
        if features.is_file():
            frame = pd.read_csv(features)
            context.update(drivers=len(frame), modified=datetime.fromtimestamp(features.stat().st_mtime, timezone.utc).isoformat())
        snapshot = source/'history'/'latest_prediction_snapshot.csv'
        if snapshot.is_file():
            row = pd.read_csv(snapshot, nrows=1).iloc[0]
            context['label'] = f"{row.get('year', '')} {row.get('event', '')} · {row.get('session', '')} (saved snapshot)"
        return {'features': features.is_file(), 'strategies': strategies.is_file(),
                'matlab': matlab_executable(), 'context': context, 'scenarios': SCENARIOS,
                'active_id': self.active_id if self.process and self.process.poll() is None else None,
                'history': self.history()}

    def _folder(self, job_id):
        existing = {'existing-experiments': self.root/'outputs/matlab/experiments',
                    'existing-laps': self.root/'outputs/matlab',
                    'existing-race': self.root/'outputs'}
        if job_id in existing:
            return existing[job_id]
        if not re.fullmatch(r'[0-9T_Z-]+_[a-f0-9]{8}', str(job_id)):
            raise ValueError('Unknown run.')
        path = self.run_root/job_id
        if not (path/'job.json').is_file():
            raise ValueError('Run not found.')
        return path

    def history(self):
        from src.app_services.run_class import classify
        with self.lock:
            rows = [self._read_job(p) for p in self.run_root.glob('*/job.json')]
        for row in rows:
            if row['status'] != 'unreadable' and row.get('kind') not in ('score', 'discord', 'historical_download', 'historical_training',
                                                                    'archive_replay'):
                row['run_class'] = classify(self.run_root/row['id'], row)['run_class']
        rows.sort(key=lambda row: row['created_at'], reverse=True)
        for key, label, relative, kind in [
            ('existing-experiments','Previous scenario experiments','outputs/matlab/experiments/scenario_comparison.csv','experiments'),
            ('existing-laps','Previous lap dynamics','outputs/matlab/lap_dynamics_summary.csv','lap_dynamics'),
            ('existing-race','Previous race forecast','outputs/simulation_summary.csv','monte_carlo')]:
            path = self.root/relative
            if path.is_file():
                rows.append({'id': key, 'label': label, 'kind': kind, 'status': 'existing',
                             'created_at': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()})
        return rows

    def start(self, payload):
        with self.lock:
            if self.process and self.process.poll() is None:
                raise ValueError('A simulation is already running. Wait or cancel it first.')
            kind = payload.get('kind', 'monte_carlo')
            if kind not in KINDS:
                raise ValueError('Unknown simulation type.')
            scenario = payload.get('scenario', 'all')
            if scenario not in SCENARIOS:
                raise ValueError('Unknown experiment scenario.')
            n_sims = int(payload.get('n_sims', 5000))
            seed = int(payload.get('seed', 42))
            difficulty = float(payload.get('overtaking_difficulty', .55))
            if not 100 <= n_sims <= 100000 or not 0 <= seed <= 2**32-1:
                raise ValueError('Use 100–100,000 races and a seed from 0 to 4,294,967,295.')
            if not math.isfinite(difficulty) or not 0 <= difficulty <= 1:
                raise ValueError('Overtaking difficulty must be between 0 and 1.')
            source = self._source(payload.get('source_dir', 'outputs'))
            input_source = payload.get('input_source', 'saved')
            if input_source not in ('saved', 'historical'):
                raise ValueError('Unknown input source.')
            historical = validate_selection(payload.get('historical', {})) if input_source == 'historical' else None
            if kind == 'forecast':
                from src.app_services.run_class import describe, protocol_changes
                changes = protocol_changes({'n_sims': n_sims, 'seed': seed, 'overtaking_difficulty': difficulty})
                if changes:
                    raise ValueError('Official forecasts use the fixed protocol (' + '; '.join(describe(changes))
                                     + '). Use What if to try other settings.')
            special = kind in ('forecast','score','discord','historical_download','historical_training','archive_replay')
            training = None
            if kind == 'historical_training':
                from src.app_services.model_training import prepare
                training = prepare(self.root, payload.get('training', {}))
            replay = None
            if kind == 'archive_replay':
                from src.app_services.archive_replay import options as replay_options
                replay = replay_options(self.root, payload.get('replay', {}))
            archive = None
            if kind == 'historical_download':
                from src.app_services.historical_library import options
                archive = options(payload.get('archive', {}))
            forecast_folder = None
            if kind in ('score','discord'):
                from src.app_services.beta import verified_snapshot
                forecast_folder = self._folder(payload.get('forecast_id'))
                verified_snapshot(forecast_folder)
                if kind == 'discord':
                    # Personal runs are never sent anywhere as if they were the forecast.
                    from src.app_services.run_class import require_official
                    require_official(forecast_folder)
                if kind == 'discord':
                    from src.app_services.discord_settings import local_webhook
                    if not local_webhook(self.root):
                        raise ValueError('Discord is not configured. Add DISCORD_WEBHOOK_URL to the local .env.discord file.')
            if not special and not historical and not (source/'driver_model_features.csv').is_file():
                raise ValueError('No driver features found. Run Race Setup first or select another output folder.')
            matlab = matlab_executable()
            if kind in ('lap_dynamics','experiments') and not matlab:
                raise ValueError('MATLAB was not found. Install MATLAB with Simulink to run this simulation.')
            if not historical and kind == 'experiments' and not (source/'strategy/predicted_tyre_strategy.csv').is_file():
                raise ValueError('Scenario experiments need predicted_tyre_strategy.csv. Run Race Setup first.')
            job_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid4().hex[:8]
            folder = self.run_root/job_id
            folder.mkdir()
            if not historical and not special:
                shutil.copy2(source/'driver_model_features.csv', folder/'features.csv')
                if (source/'strategy/predicted_tyre_strategy.csv').is_file():
                    shutil.copy2(source/'strategy/predicted_tyre_strategy.csv', folder/'strategies.csv')
            data = {'id': job_id, 'label': KINDS[kind], 'kind': kind, 'scenario': scenario,
                    'input_source':input_source, 'historical':historical,
                    'status': 'running', 'created_at': datetime.now(timezone.utc).isoformat(),
                    'source_dir': str(source), 'n_sims': n_sims, 'seed': seed,
                    'overtaking_difficulty': difficulty, 'matlab': matlab,
                    'note': 'Uses saved features. Monte Carlo uses neutral weather modifiers; Simulink uses exploratory fuel/tyre assumptions.'}
            if special:
                data['historical'] = None
                data['source_dir'] = str(folder/'source')
                data['forecast_folder'] = str(forecast_folder) if forecast_folder else None
                if archive:
                    data['archive'] = archive
                    data['label'] += ' · ' + ', '.join(map(str, archive['years']))
                    data['note'] = 'Downloads and checkpoints historical data locally. Does not train or change the prediction model.'
                if replay:
                    data.update(replay=replay, n_sims=replay['n_sims'], seed=replay['seed'])
                    data['label'] += ' · ' + ', '.join(map(str, replay['years']))
                    data['note'] = 'Retrospective: past races forecast again from the historical library. Kept apart from the official record.'
                if training:
                    write_json(folder/'training_selection.json', training)
                    data['training'] = {'years': training['years'], 'races': len(training['races'])}
                    data['label'] += ' · ' + ', '.join(map(str, training['years']))
                    data['note'] = 'Offline candidate training with chronological validation. Live model artifacts and forecast settings are unchanged.'
            elif historical:
                data['label'] += f" · {historical['year']} {historical['event']} · {historical['session']}"
                data['source_dir'] = str(folder/'source')
                data['note'] = 'Historical replay, not an out-of-sample backtest. Live forecasts and trained calibration disabled; other model assumptions and reference tables remain current.'
            else:
                snapshot = source/'history/latest_prediction_snapshot.csv'
                if snapshot.is_file():
                    context = pd.read_csv(snapshot, nrows=1)
                    if not context.empty:
                        row = context.iloc[0]
                        data['label'] += f" · {row.get('year', '')} {row.get('event', '')} · {row.get('session', '')}"
            write_json(folder/'job.json', data)
            self._launch(folder, job_id)
            return {'id': job_id}

    def start_manual(self, config):
        """Internal Race Setup entry point, using the same cancellable worker."""
        with self.lock:
            if self.process and self.process.poll() is None:
                raise ValueError('A simulation is already running. Wait or cancel it first.')
            if config['outputs'].get('post_to_discord'):
                raise ValueError('Manual runs cannot publish to Discord.')
            output = Path(config['outputs']['output_dir']).resolve()
            if output.is_relative_to(self.run_root) or 'frozen' in {p.lower() for p in output.parts}:
                raise ValueError('Choose a separate output directory.')
            job_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid4().hex[:8]
            folder = self.run_root/job_id
            folder.mkdir()
            write_json(folder/'manual_config.json', config)
            write_json(folder/'job.json', {'id': job_id, 'kind': 'manual_run',
                'label': 'Race Setup', 'status': 'running',
                'created_at': datetime.now(timezone.utc).isoformat(),
                'output_dir': str(output), 'source_dir': str(output),
                'note': 'Manual run in a managed, cancellable worker.'})
            self._launch(folder, job_id)
            return {'id': job_id, 'configPath': str(folder/'manual_config.json')}

    def _launch(self, folder, job_id):
        command = [sys.executable, '-u', '-m', 'portable_app.job_worker', str(folder)]
        if getattr(sys, 'frozen', False):
            command = [sys.executable, '--job-worker', str(folder)]
        try:
            worker_env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
            if not getattr(sys, 'frozen', False):
                # Source --workspace launches still import code from this
                # checkout, while writing downloads into the chosen workspace.
                worker_env['PYTHONPATH'] = os.pathsep.join(filter(None,
                    [str(Path(__file__).resolve().parents[2]), os.environ.get('PYTHONPATH')]))
            with (folder/'run.log').open('w', encoding='utf-8') as log:
                self.process = subprocess.Popen(command, cwd=self.root, stdout=log, stderr=subprocess.STDOUT,
                    env=worker_env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except Exception as exc:
            data = self._read_job(folder/'job.json')
            data.update(status='failed', error=str(exc))
            write_json(folder/'job.json', data)
            raise
        self.active_id = job_id
        threading.Thread(target=self._wait, args=(job_id, self.process), daemon=True).start()

    def _wait(self, job_id, process):
        code = process.wait()
        with self.lock:
            path = self._folder(job_id)/'job.json'
            data = json.loads(path.read_text(encoding='utf-8'))
            data['status'] = 'cancelled' if data['status'] in {'cancelling', 'cancelled'} else ('completed' if code == 0 else 'failed')
            download_result = path.parent/'download_result.json'
            if data.get('kind') == 'historical_download' and code == 0 and data['status'] != 'cancelled' and download_result.is_file():
                data['status'] = json.loads(download_result.read_text(encoding='utf-8'))['status']
            context_path = path.parent/'forecast_context.json'
            if context_path.is_file():
                context = json.loads(context_path.read_text(encoding='utf-8'))
                data['label'] = f"Next race · {context['year']} {context['event']} · {context['session']}"
            failure = path.parent/'failure.json'
            if data['status'] == 'failed' and failure.is_file():
                try:
                    data['error'] = json.loads(failure.read_text(encoding='utf-8'))['message']
                except (OSError, ValueError, KeyError):
                    pass
            data.update(exit_code=code, finished_at=datetime.now(timezone.utc).isoformat())
            write_json(path, data)

    def cancel(self):
        with self.lock:
            if not self.process or self.process.poll() is not None:
                return False
            path = self._folder(self.active_id)/'job.json'
            data = json.loads(path.read_text(encoding='utf-8'))
            data['status'] = 'cancelling'
            write_json(path, data)
            if data.get('kind') == 'historical_download':
                (path.parent/'stop_requested').write_text('Stop after the current session.', encoding='utf-8')
                return True
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'],
                    capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, check=True)
            else:
                self.process.terminate()
            # Persist cancellation before a window-close callback lets the app exit.
            code = self.process.wait(timeout=10)
            data.update(status='cancelled', exit_code=code,
                        finished_at=datetime.now(timezone.utc).isoformat())
            write_json(path, data)
            return True

    def status(self, job_id):
        folder = self._folder(job_id)
        with self.lock:
            path = folder/'job.json'
            data = self._read_job(path) if path.is_file() else {'id': job_id, 'status': 'existing'}
        log = folder/'run.log'
        data['log'] = ''
        if log.is_file():
            with log.open('rb') as stream:
                stream.seek(max(0, log.stat().st_size-100000))
                data['log'] = stream.read().decode('utf-8', errors='replace')
        progress = re.findall(r'Completed (\d+) of (\d+) simulation runs', data['log'])
        data['progress'] = list(map(int, progress[-1])) if progress else None
        source = folder/'source'
        data['reusable_source'] = str(source.relative_to(self.root)) if data.get('status') == 'completed' and (source/'driver_model_features.csv').is_file() else None
        context = folder/'forecast_context.json'
        if context.is_file():
            forecast = json.loads(context.read_text(encoding='utf-8'))
            data['label'] = f"Next race · {forecast['year']} {forecast['event']} · {forecast['session']}"
            data['forecast_context'] = forecast
        data['frozen'] = (folder/'frozen/manifest.json').is_file()
        if data['frozen']:
            from src.app_services.beta import verified_snapshot
            try:
                verified_snapshot(folder)
            except (ValueError, KeyError, OSError) as exc:
                data['frozen'] = False
                data['snapshot_error'] = str(exc)
        data['score'] = json.loads((folder/'score.json').read_text(encoding='utf-8')) if (folder/'score.json').is_file() else None
        progress = folder/'download_progress.json'
        if data.get('kind') == 'historical_download' and progress.is_file():
            data['archive_progress'] = json.loads(progress.read_text(encoding='utf-8'))
        if data.get('kind') == 'historical_download':
            from src.app_services.request_meter import request_usage
            try:
                data['request_usage'] = request_usage(self.root, folder)
            except (OSError, ValueError, KeyError, TypeError):
                data['request_usage'] = {'status': 'unavailable', 'reason': 'Request monitoring data is unavailable.',
                                         'providers': [], 'guards': []}
        progress = folder/'replay_progress.json'
        if data.get('kind') == 'archive_replay' and progress.is_file():
            data['replay_progress'] = json.loads(progress.read_text(encoding='utf-8'))
        progress = folder/'training_progress.json'
        if data.get('kind') == 'historical_training':
            if progress.is_file():
                data['training_progress'] = json.loads(progress.read_text(encoding='utf-8'))
            if data['status'] == 'completed':
                from src.app_services.model_training import result
                data['training_result'] = result(folder)
        return data

    def results(self, job_id, driver='', scenario=''):
        folder = self._folder(job_id)
        name = next((n for n in ['score_comparison.csv','scenario_comparison.csv','lap_dynamics_summary.csv','simulation_summary.csv'] if (folder/n).is_file()), None)
        if name is None:
            return {'rows': [], 'drivers': [], 'scenarios': [], 'laps': [], 'verification': {}}
        frame = pd.read_csv(folder/name)
        drivers = sorted(frame.Driver.dropna().unique().tolist())
        scenarios = sorted(frame.scenario.dropna().unique().tolist()) if 'scenario' in frame else []
        if driver:
            frame = frame[frame.Driver.eq(driver)]
        if scenario and 'scenario' in frame:
            frame = frame[frame.scenario.eq(scenario)]
        desired = ['Driver','Team','scenario','simulated_rank','avg_finish','win_chance','podium_chance',
                   'dnf_chance','avg_points','simulated_race_time_seconds','delta_vs_baseline_seconds','pit_stops','actual_position','finish_error']
        rows = records(frame[[c for c in desired if c in frame]])
        laps = []
        detail = folder/'lap_dynamics_results.csv'
        chart_driver = driver or (drivers[0] if drivers else '')
        if detail.is_file() and chart_driver:
            data = pd.read_csv(detail)
            data = data[data.Driver.eq(chart_driver)]
            if 'scenario' in data:
                data = data[data.scenario.isin(['baseline', scenario or 'baseline'])]
            laps = records(data.head(5000))
        check = folder/'verification.json'
        verification = json.loads(check.read_text(encoding='utf-8')) if check.is_file() else {}
        if verification.get('status') == 'PASS':
            for filename, key in [('experiment_inputs.csv', 'inputs_sha256'),
                                  ('lap_dynamics_results.csv', 'detail_sha256'),
                                  ('lap_dynamics_summary.csv', 'summary_sha256')]:
                path = folder/filename
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != verification.get(key):
                    verification = {'status': 'STALE', 'reason': 'Files changed since verification.'}
                    break
        return {'rows': rows, 'drivers': drivers, 'scenarios': scenarios, 'laps': laps, 'verification': verification,
                'folder': str(folder), 'row_count': len(frame), 'chart_driver': chart_driver}

    def export(self, job_id, driver='', scenario=''):
        rows = self.results(job_id, driver, scenario)['rows']
        if not rows:
            raise ValueError('No result rows to export.')
        folder = self._folder(job_id)/'exports'
        folder.mkdir(exist_ok=True)
        path = folder/f"results_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{uuid4().hex[:8]}.csv"
        pd.DataFrame(rows).to_csv(path, index=False)
        return {'filename': path.name, 'path': str(path), 'rows': len(rows)}

    def open_folder(self, job_id):
        path = self._folder(job_id)
        if os.name == 'nt':
            os.startfile(path)
        else:
            subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(path)])
        return True
