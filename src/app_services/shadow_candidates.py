"""Independent, local candidate arms using pinned pre-race history."""
from __future__ import annotations

from dataclasses import asdict
import gzip
from io import StringIO
import json
from types import SimpleNamespace

import pandas as pd

from src.agent_race import AgentSettings
from src.app_services.practice_collection import utc
from src.pit_scenarios import assumed_plans, inventory_plans
from src.qualifying_pace import apply_qualifying_pace, fit_qualifying_pace
from src.retirement_survival import attach_survival_risk

CANDIDATES = ('pit_scenarios_v1', 'survival_dnf_v1',
              'qualifying_partial_pooling_v1', 'agent_laps_v1',
              'agent_neutralisation_v1', 'pit_inventory_v1')
CONTROL = 'candidate_control'
BASELINES = {'agent_neutralisation_v1': 'agent_laps_v1', 'pit_inventory_v1': 'pit_scenarios_v1'}


def write_history(path, races, *, captured_at):
    """Create an immutable, portable snapshot; never pickle runtime inputs."""
    def frame(value):
        value = pd.DataFrame(value)
        return {'data': json.loads(value.to_json(orient='split', date_format='iso', double_precision=15)),
                'timedeltas': [c for c in value if pd.api.types.is_timedelta64_dtype(value[c])],
                'datetimes': [c for c in value if pd.api.types.is_datetime64_any_dtype(value[c])]}
    def table(session, name):
        try:
            return frame(getattr(session, name, pd.DataFrame()))
        except Exception:
            if name not in ('weather_data', 'track_status', 'race_control_messages', 'session_status'):
                raise
            return frame(pd.DataFrame())
    rows = []
    for metadata, sessions in races:
        rows.append({'metadata': metadata, 'sessions': {
            code: {name: table(session, name)
                   for name in ('laps', 'results', 'weather_data', 'track_status',
                                'race_control_messages', 'session_status')}
            for code, session in sessions.items() if code in ('Q', 'R')}})
    payload = {'schema_version': 1, 'captured_at_utc': utc(captured_at).isoformat(), 'races': rows,
               'policy': 'Fixed history for this suite; no online archive updates or hyperparameter tuning.'}
    with path.open('xb') as handle:
        handle.write(gzip.compress(json.dumps(payload, allow_nan=False).encode('utf-8'), mtime=0))


def read_history(path, context):
    packet = json.loads(gzip.decompress(path.read_bytes()))
    cutoff = context.get('history_cutoff_utc', context['data_cutoff_utc'])
    if packet.get('schema_version') != 1 or utc(packet['captured_at_utc']) > utc(cutoff):
        raise ValueError('History packet must exist before the declared history cutoff.')
    target = int(context['year']), int(context['round'])
    rows = []; keys = set()
    for row in packet['races']:
        metadata = row['metadata']; key = int(metadata['year']), int(metadata['round'])
        if key in keys:
            raise ValueError('Duplicate pinned history race.')
        keys.add(key)
        if key >= target:
            continue
        sessions = {}
        for code, tables in row['sessions'].items():
            values = {}
            for name, saved in tables.items():
                data = saved['data']
                frame = pd.DataFrame(data['data'], columns=data['columns'], index=data['index'])
                for column in saved['timedeltas']:
                    frame[column] = pd.to_timedelta(frame[column], errors='raise')
                for column in saved['datetimes']:
                    frame[column] = pd.to_datetime(frame[column], errors='raise')
                values[name] = frame
            sessions[code] = SimpleNamespace(**values)
        if 'R' in sessions:
            rows.append((metadata, sessions))
    if not rows:
        raise ValueError('No strictly earlier races in the pinned history packet.')
    return sorted(rows, key=lambda r: (r[0]['year'], r[0]['round']))


def prepare_candidate(name, features, inputs, context, history_path=None, tyre_inventory=None, tyre_ledger=None):
    """Return exact features/settings to freeze with each successful prediction."""
    frame = features.copy(); options = dict(inputs); evidence = {}
    if name in ('pit_scenarios_v1', 'agent_laps_v1', 'agent_neutralisation_v1', 'pit_inventory_v1'):
        if (inputs.get('weather_modifiers') or {}).get('rainfall_flag'):
            raise ValueError('Dry-only candidate; source forecast indicates rain.')
        options['pit_plans'] = assumed_plans(frame, frame.estimated_race_laps.median())
    if name in ('agent_laps_v1', 'agent_neutralisation_v1'):
        options['agent_settings'] = asdict(AgentSettings(step_seconds=1., season_year=int(context['year']),
            passability=1. - float(inputs.get('overtaking_difficulty', .55))))
        if name == 'agent_neutralisation_v1':
            if history_path is None:
                raise ValueError('No pinned neutralisation history packet registered.')
            from src.neutralisation import fit_neutralisation
            model = fit_neutralisation(read_history(history_path, context), context)
            options['agent_settings']['neutralisation_model'] = model
            evidence['neutralisation_model'] = model
    elif name == 'pit_inventory_v1':
        options['pit_plans'] = inventory_plans(frame, frame.estimated_race_laps.median(), tyre_inventory, tyre_ledger)
        evidence['tyre_policy'] = 'Frozen estimated fresh sets plus at most one used set per compound; used availability assumed.'
    elif name in ('survival_dnf_v1', 'qualifying_partial_pooling_v1'):
        if name == 'qualifying_partial_pooling_v1' and context['session'] != 'Q':
            raise ValueError('Post-qualifying candidate; requires the Q stage.')
        if history_path is None:
            raise ValueError('No pinned history packet registered for this suite.')
        history = read_history(history_path, context)
        if name == 'survival_dnf_v1':
            recent = history[-30:]
            frame = attach_survival_risk(frame, [(s['R'], m) for m, s in recent], context)
            if frame.retirement_known_observations.min() <= 0:
                raise ValueError('No known retirement observations in the pinned history.')
            options['retirement_classification'] = 'completed_laps_v1'
            evidence['history_races'] = [[m['year'], m['round']] for m, _ in recent]
        else:
            if not {'q_rank','q_best_lap','q_gap_to_best'}.issubset(frame):
                raise ValueError('Source forecast has no frozen official Q features; a new Q forecast is required.')
            eligible = [(m,s) for m,s in history if 'Rainfall' in s['R'].weather_data
                and s['R'].weather_data.Rainfall.notna().any()]
            model = fit_qualifying_pace([(s.get('Q'), s['R'], m) for m, s in eligible], context)
            frame = apply_qualifying_pace(frame, model, context)
            options['sample_pace_posterior'] = True
            evidence['pace_model'] = model
    elif name not in ('pit_scenarios_v1', CONTROL):
        raise ValueError('Unknown shadow candidate.')
    return frame, options, evidence
