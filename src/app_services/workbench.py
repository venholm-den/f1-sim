"""Read-only dashboard inputs and additive exports for the portable workbench."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

from src.app_services.data_health import DATA_SOURCE_REQUIREMENTS, validate_data_sources
from src.app_services.output_index import read_output_table


def payload(frame: pd.DataFrame) -> dict:
    return {'columns': frame.columns.tolist(), 'rows': json.loads(frame.to_json(orient='records'))}


def data_preview(config: dict, key: str, page: int = 1) -> dict:
    if key not in DATA_SOURCE_REQUIREMENTS:
        raise ValueError('Choose one of the configured data sources.')
    statuses = validate_data_sources(config)
    status = next(item for item in statuses if item.key == key)
    page = max(1, min(int(page), max(1, (status.row_count + 9) // 10)))
    frame = pd.DataFrame()
    if status.exists and status.status == 'valid':
        if key == 'fia_document_index':
            from src.data_sources.fia_extraction import published_utc
            frame = pd.read_csv(status.path)
            if 'published_at' in frame:
                frame['_published_utc'] = pd.to_datetime(frame.published_at.map(published_utc),utc=True,errors='coerce')
                frame = frame.sort_values('_published_utc',ascending=False,na_position='last',kind='stable').drop(columns='_published_utc')
            frame = frame.iloc[(page - 1) * 10:page * 10]
        else:
            frame = pd.read_csv(status.path, nrows=page * 10).iloc[(page - 1) * 10:page * 10]
    return {**payload(frame), 'source': status.__dict__, 'page': page,
            'pages': max(1, (status.row_count + 9) // 10),
            'sort': {'column':'published_at','direction':'desc'} if key=='fia_document_index' else None,
            'checked_at_utc': datetime.now(timezone.utc).isoformat()}


def model_reference() -> dict:
    from src.model import CURRENT_SESSION_WEIGHTS
    from src.model_config import MODEL_VERSION, SESSION_WEIGHTS, FANTASY_SCORING
    return {'version': MODEL_VERSION, 'current_session_weights': CURRENT_SESSION_WEIGHTS,
            'signal_weights': SESSION_WEIGHTS, 'fantasy_scoring': FANTASY_SCORING,
            'weight_editing_supported': False, 'confidence_probability_available': False}


def saved_details(output_dir: str | Path, summary_override=None) -> dict:
    root = Path(output_dir)
    def read(name):
        try:
            value = json.loads((root/name).read_text(encoding='utf-8'))
            return value if isinstance(value, dict) else {}
        except (ValueError, OSError):
            return {}
    matrix = read_output_table(root, 'position_matrix.csv', max_rows=100)
    summary = summary_override if summary_override is not None else read_output_table(root, 'simulation_summary.csv', max_rows=100)
    fantasy_columns = ['Driver', 'Team', 'avg_fantasy_points', 'fantasy_ceiling_p90', 'fantasy_floor_p10',
                       'fantasy_price', 'fantasy_xppm']
    fantasy = summary[[key for key in fantasy_columns if key in summary]].copy()
    if 'avg_fantasy_points' in fantasy:
        fantasy = fantasy.sort_values('avg_fantasy_points', ascending=False)
    weather = read('race_weather.json')
    # Automated run details sit under source/, while its race forecast is archived
    # next to it. Match only that run; never substitute a different event's weather.
    if not weather and root.name == 'source':
        parent = root.parent/'race_weather.json'
        try:
            weather = json.loads(parent.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            pass
    saved_run = read('ui_run.json')
    forecast_config = read('forecast_config.json')
    if root.name == 'source' and (root.parent/'frozen/forecast_config.json').is_file():
        try:
            forecast_config = json.loads((root.parent/'frozen/forecast_config.json').read_text(encoding='utf-8'))
        except (ValueError, OSError):
            pass
    return {'positionMatrix': payload(matrix), 'fantasyTable': payload(fantasy),
            'venue': read('venue_context.json'), 'raceWeather': weather,
            'run': saved_run, 'forecastRun': forecast_config.get('run', {}),
            'risk': {column: float(pd.to_numeric(summary[column], errors='coerce').mean())
                     for column in ('red_flag_chance', 'dnf_chance')
                     if column in summary and pd.to_numeric(summary[column], errors='coerce').notna().any()},
            'confidence': None}


def validate_settings(settings) -> None:
    checks = [(2018 <= settings.year <= datetime.now(timezone.utc).year + 1, 'Select a supported season.'),
              (1 <= settings.n_sims <= 100000, 'Use 1–100,000 simulations.'),
              (0 <= settings.random_seed <= 4294967295, 'Seed must be between 0 and 4294967295.'),
              (1 <= settings.n_baseline_races <= 24, 'Use 1–24 baseline races.'),
              (0 <= settings.historical_strategy_lookback_years <= 20, 'Use 0–20 history years.'),
              (0 <= settings.default_overtaking_difficulty <= 1, 'Overtaking difficulty must be between 0 and 1.'),
              (0 <= settings.historical_finish_weight <= .6, 'Finish calibration weight must be between 0 and 0.6.'),
              (0 <= settings.historical_dnf_weight <= .75, 'DNF calibration weight must be between 0 and 0.75.'),
              (settings.session in {'PRE', 'FP1', 'FP2', 'FP3', 'Q', 'SQ', 'S', 'R'}, 'Select a supported session.')]
    for valid, message in checks:
        if not valid:
            raise ValueError(message)


def export_results(output_dir: str | Path, kind: str) -> dict:
    root = Path(output_dir).resolve()
    choices = {'csv': ['simulation_summary.csv', 'position_matrix.csv'],
               'snapshot': ['history/latest_prediction_snapshot.csv', 'venue_context.json', 'ui_run.json'],
               'images': ['report/race_dashboard.png', 'report/tyre_strategy_timeline.png',
                          'report/fantasy_risk_reward.png', 'probabilities.png', 'forecast_outlook.png', 'finish_ranges.png']}
    if kind not in choices:
        raise ValueError('Choose CSV, snapshot or images.')
    sources = [root/name for name in choices[kind] if (root/name).is_file()]
    if kind == 'snapshot' and not (root/'history/latest_prediction_snapshot.csv').is_file():
        raise ValueError('No prediction snapshot was saved. Enable the snapshot output for your next run.')
    if not sources:
        raise ValueError('These outputs are unavailable. Enable them on Race Setup and run the simulation.')
    if 'frozen' in {part.lower() for part in root.parts}:
        raise ValueError('Open the containing run to export; frozen folders remain read-only.')
    destination = root/'exports'/f'{kind}-{uuid4().hex[:8]}'
    destination.mkdir(parents=True, exist_ok=False)
    for source in sources:
        shutil.copy2(source, destination/source.name)
    return {'folder': str(destination), 'files': [path.name for path in sources], 'uploaded': False}


def compare_summaries(first: pd.DataFrame, second: pd.DataFrame) -> dict:
    for frame in (first, second):
        if 'Driver' not in frame or frame.Driver.isna().any() or frame.Driver.duplicated().any():
            raise ValueError('Both runs need a complete, unique driver summary.')
    if set(first.Driver) != set(second.Driver):
        raise ValueError('Driver coverage differs. Select two runs with the same driver roster.')
    columns = [key for key in ('avg_finish', 'win_chance', 'podium_chance', 'avg_fantasy_points')
               if key in first and key in second]
    if not columns:
        raise ValueError('No comparable race metrics are available.')
    result = first[['Driver', *columns]].merge(second[['Driver', *columns]], on='Driver',
                                               suffixes=('_A', '_B'), validate='one_to_one')
    for column in columns:
        difference = pd.to_numeric(result[column+'_B'], errors='coerce') - pd.to_numeric(result[column+'_A'], errors='coerce')
        result[column + ('_delta_pp' if 'chance' in column else '_delta')] = difference * (100 if 'chance' in column else 1)
    return payload(result)
