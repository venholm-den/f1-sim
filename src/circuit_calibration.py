"""Offline, inactive circuit evidence; never writes live profiles or forecasts.

SC/red rates are race-window event probabilities. Lap-order reversals are a
restricted timing proxy, not official overtakes or a fitted simulation weight.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta, gamma

from src.venues import CIRCUITS, resolve_venue

DEFAULTS = {'safety_car': .40, 'red_flag': .035}
PRIOR_RACES = 4.0
PROXY_PRIOR_EXPOSURE = 500.0
TABLES = {'laps', 'track_status', 'session_status'}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_tables(manifest_path, manifest):
    """Verify only consumed tables, avoiding expensive unrelated telemetry reads."""
    folder = manifest_path.parent.resolve()
    frames, sources = {}, []
    for name, info in manifest.get('files', {}).items():
        table = info.get('table')
        if table not in TABLES:
            continue
        if table in frames:
            raise ValueError(f'Duplicate {table} table')
        file = (folder / name).resolve()
        if not file.is_relative_to(folder) or not file.is_file():
            raise ValueError(f'Invalid {table} path')
        if file.stat().st_size != info['bytes'] or sha256(file) != info['sha256']:
            raise ValueError(f'Changed {table} file')
        frames[table] = pd.read_csv(file)
        sources.append({'table': table, 'path': str(file), 'sha256': info['sha256']})
    return frames, sources


def status_code(value):
    # CSV numeric inference can turn a code such as 1 into 1.0.
    return str(value).strip().removesuffix('.0')


def race_events(laps, track_status):
    """Step-state status at first lap start, through first finish on the last lap.

    No track feed/initial state means unknown, never an event-free race. The
    envelope includes suspensions/restarts but excludes ended pre-start events.
    """
    needed = {'LapStartTimeSeconds', 'LapTimeSeconds', 'LapNumber'}
    if not needed <= set(laps) or not {'Time', 'Status'} <= set(track_status):
        return None, 'missing lap timing or track-status feed'
    data = laps[list(needed)].apply(pd.to_numeric, errors='coerce').dropna()
    data = data[(data.LapTimeSeconds > 0) & (data.LapNumber >= 1)]
    if data.empty or data.LapNumber.max() < 3:
        return None, 'insufficient racing laps'
    start = float(data.LapStartTimeSeconds.min())
    last = data[data.LapNumber == data.LapNumber.max()]
    end = float((last.LapStartTimeSeconds + last.LapTimeSeconds).min())
    feed = pd.DataFrame({'time': pd.to_timedelta(track_status.Time, errors='coerce').dt.total_seconds(),
                         'code': track_status.Status.map(status_code)}).dropna(subset=['time'])
    feed = feed.sort_values('time', kind='stable')
    initial = feed[feed.time <= start].tail(1)
    if initial.empty or end <= start:
        return None, 'track-status initial state unavailable'
    window = pd.concat([initial, feed[(feed.time > start) & (feed.time <= end)]])
    if not set(window.code) <= {'1', '2', '3', '4', '5', '6', '7'}:
        return None, 'unknown track-status code in race window'
    return {'safety_car': int('4' in set(window.code)),
            'red_flag': int('5' in set(window.code)),
            'virtual_safety_car': int(bool({'6', '7'} & set(window.code))),
            'race_start_seconds': start, 'race_end_seconds': end}, None


def clean_order_changes(laps):
    """Count nearby adjacent-pair reversals over two fully clean green laps.

    Compare the same numbered lap at the line, excluding opening lap, pits,
    deleted/inaccurate laps and non-green track codes. This misses within-lap
    passes reversed before the line and is not a certified overtake count.
    """
    required = {'Driver', 'LapNumber', 'LapStartTimeSeconds', 'LapTimeSeconds',
                'IsAccurate', 'PitIn', 'PitOut', 'Deleted', 'TrackStatus'}
    if not required <= set(laps):
        return {'changes': None, 'exposure': 0, 'reason': 'required timing/quality fields unavailable'}
    d = laps.copy()
    for col in ('LapNumber', 'LapStartTimeSeconds', 'LapTimeSeconds'):
        d[col] = pd.to_numeric(d[col], errors='coerce')
    if d.duplicated(['Driver', 'LapNumber']).any():
        return {'changes': None, 'exposure': 0, 'reason': 'duplicate driver/lap observations'}
    truth = lambda s: s.astype(str).str.strip().str.lower().isin(['true', '1', '1.0'])
    false = lambda s: s.astype(str).str.strip().str.lower().isin(['false', '0', '0.0'])
    d['clean'] = (truth(d.IsAccurate) & false(d.PitIn) & false(d.PitOut) & false(d.Deleted)
                  & d.TrackStatus.map(status_code).eq('1'))
    d['end'] = d.LapStartTimeSeconds + d.LapTimeSeconds
    d = d.dropna(subset=['Driver', 'LapNumber', 'end'])
    d = d[d.LapTimeSeconds > 0]
    by_lap = {int(n): g.set_index('Driver') for n, g in d.groupby('LapNumber')}
    changes = exposure = 0
    for n, current in by_lap.items():
        if n < 3 or n-1 not in by_lap:
            continue
        previous = by_lap[n-1].sort_values('end')
        drivers = list(previous.index)
        for a, b in zip(drivers, drivers[1:]):
            if a not in current.index or b not in current.index:
                continue
            four = [previous.loc[a], previous.loc[b], current.loc[a], current.loc[b]]
            if not all(bool(row['clean']) for row in four):
                continue
            prior_gap = previous.loc[b, 'end'] - previous.loc[a, 'end']
            gap = current.loc[b, 'end'] - current.loc[a, 'end']
            if not 0 < prior_gap <= 15 or not 0 < abs(gap) <= 15:
                continue
            exposure += 1
            changes += int(gap < 0)
    return {'changes': changes if exposure else None, 'exposure': exposure,
            'reason': None if exposure else 'no eligible nearby green pair-laps'}


def calibration_venue(manifest):
    """Use saved identity; an explicit local Yas Island alias repairs no archive."""
    venue = manifest.get('venue', {})
    if venue.get('venue_status') == 'conflict':
        return venue, 'saved_conflict'
    if venue.get('circuit_id') and venue.get('layout_id'):
        result, source = dict(venue), 'saved_venue'
    elif (manifest['event'] == 'Abu Dhabi Grand Prix'
          and venue.get('feed_location') == 'Yas Island' and not venue.get('feed_circuit_hint')):
        result = resolve_venue(manifest['year'], manifest['event'], location='Yas Marina')
        source = 'explicit_yas_island_alias'
    else:
        # Re-resolve with the reviewed registry, retaining feed constraints and
        # leaving original manifests byte-for-byte intact. Never discard hints.
        result = resolve_venue(manifest['year'], manifest['event'],
            location=venue.get('feed_location'), circuit_hint=venue.get('feed_circuit_hint'))
        source = 'reviewed_registry_with_saved_feed_hints'
        if result.get('venue_status') != 'resolved':
            return venue, 'unresolved_saved_venue'
    # Melbourne's redesign falls inside our observation period. Never pool
    # pre-2022 evidence into this regime, even if an older registry omitted it.
    if result['circuit_id'] == 'albert_park':
        result['layout_id'] = 'albert_park_since_2022' if manifest['year'] >= 2022 else 'albert_park_pre_2022'
    return result, source


def observations(workspace, years):
    rows, excluded = [], []
    paths = sorted((Path(workspace)/'data/historical_library').glob('*/detailed/*/session.json'))
    manifests = [(p, json.loads(p.read_text(encoding='utf-8'))) for p in paths]
    manifests = [(p, m) for p, m in manifests if m.get('year') in years
                 and m.get('session') == 'R' and m.get('status') == 'complete']
    keys = Counter((m['year'], m['round']) for _, m in manifests)
    for path, m in manifests:
        identity = {key: m.get(key) for key in ('year', 'round', 'event')}
        try:
            key = m['year'], m['round']
            if keys[key] != 1:
                raise ValueError('duplicate year/round archive partitions')
            venue, source = calibration_venue(m)
            if not venue.get('circuit_id') or not venue.get('layout_id'):
                raise ValueError('unresolved/conflicting physical circuit identity')
            if venue.get('race_quality', {}).get('training_eligible') is False:
                raise ValueError('aborted classification excluded from ordinary race probabilities')
            tables, sources = read_tables(path, m)
            laps = tables.get('laps', pd.DataFrame())
            events, reason = race_events(laps, tables.get('track_status', pd.DataFrame()))
            proxy = clean_order_changes(laps)
            if events is None and proxy['changes'] is None:
                raise ValueError(reason or proxy['reason'])
            rows.append(identity | {'circuit_id': venue['circuit_id'], 'layout_id': venue['layout_id'],
                'circuit_name': venue.get('circuit_name'), 'venue_source': source,
                'events': events, 'events_unavailable_reason': reason, 'order_change_proxy': proxy,
                'session_status_available': 'session_status' in tables,
                'manifest_path': str(path.resolve()), 'manifest_sha256': sha256(path), 'sources': sources})
        except (ValueError, KeyError, OSError, pd.errors.ParserError) as exc:
            excluded.append(identity | {'reason': str(exc), 'manifest_path': str(path.resolve())})
    return sorted(rows, key=lambda r: (r['year'], r['round'])), excluded


def posterior(history, layout, metric):
    all_values = [r['events'][metric] for r in history if r.get('events') is not None]
    local = [r['events'][metric] for r in history if r['layout_id'] == layout and r.get('events') is not None]
    pooled = (sum(all_values) + DEFAULTS[metric]*PRIOR_RACES) / (len(all_values)+PRIOR_RACES)
    a = sum(local) + pooled*PRIOR_RACES
    b = len(local)-sum(local) + (1-pooled)*PRIOR_RACES
    return {'mean': a/(a+b), 'low90': float(beta.ppf(.05, a, b)),
            'high90': float(beta.ppf(.95, a, b)), 'races': len(local),
            'events': sum(local), 'pooled_mean': pooled}


def proxy_posterior(history, layout):
    eligible = [r for r in history if r['order_change_proxy']['changes'] is not None]
    local = [r for r in eligible if r['layout_id'] == layout]
    exposure = sum(r['order_change_proxy']['exposure'] for r in local)
    changes = sum(r['order_change_proxy']['changes'] for r in local)
    pooled_exposure = sum(r['order_change_proxy']['exposure'] for r in eligible)
    if not exposure or not pooled_exposure:
        return {'races': 0, 'exposure': 0, 'changes': None, 'mean_per_1000': None}
    # One pooled pseudo-change avoids a degenerate zero-rate prior.
    pool = (sum(r['order_change_proxy']['changes'] for r in eligible)+1)/(pooled_exposure+1)
    shape = changes + pool*PROXY_PRIOR_EXPOSURE
    rate = exposure + PROXY_PRIOR_EXPOSURE
    return {'races': len(local), 'exposure': exposure, 'changes': changes,
            'mean_per_1000': 1000*shape/rate,
            'low90_per_1000': float(1000*gamma.ppf(.05, shape, scale=1/rate)),
            'high90_per_1000': float(1000*gamma.ppf(.95, shape, scale=1/rate))}


def benchmark(rows, active):
    predictions = []
    for i, row in enumerate(rows):
        if row['year'] < 2022 or row.get('events') is None:
            continue
        history = rows[:i]
        for metric, default in DEFAULTS.items():
            estimate = posterior(history, row['layout_id'], metric)
            current = active.get((row['circuit_id'], metric), default)
            for variant, p in [('generic_default', default), ('active_profile', current),
                               ('earlier_races_pooled', estimate['pooled_mean']),
                               ('earlier_layout_shrinkage', estimate['mean'])]:
                y = row['events'][metric]
                predictions.append({k: row[k] for k in ('year', 'round', 'event', 'layout_id')} |
                    {'metric': metric, 'variant': variant, 'prediction': p, 'outcome': y,
                     'prior_layout_races': estimate['races'], 'brier': (p-y)**2,
                     'log_loss': -float(y*np.log(p)+(1-y)*np.log(1-p))})
    scores = []
    frame = pd.DataFrame(predictions)
    if not frame.empty:
        for period, mask in [('all_diagnostic', frame.year >= 2022),
                             ('through_2025', frame.year <= 2025), ('2026_rolling_diagnostic', frame.year == 2026)]:
            for (metric, variant), group in frame[mask].groupby(['metric', 'variant']):
                scores.append({'period': period, 'metric': metric, 'variant': variant, 'races': len(group),
                    'brier': float(group.brier.mean()), 'log_loss': float(group.log_loss.mean())})
    return predictions, scores


def build_report(workspace, years, profiles_path):
    rows, excluded = observations(workspace, years)
    if not rows:
        raise ValueError('No usable archived race observations; no report generated')
    profiles = pd.read_csv(profiles_path).fillna('')
    active = {}
    for _, row in profiles.iterrows():
        for metric, column in [('safety_car', 'SafetyCarChance'), ('red_flag', 'RedFlagBaseChance')]:
            value = float(row[column])
            if not 0 < value < 1:
                raise ValueError(f'Invalid active {column}')
            active[row.CircuitId, metric] = value
    predictions, scores = benchmark(rows, active)
    candidates = []
    latest_year = max(years)
    # Every reference circuit is represented, including no-data historical tracks.
    for _, profile in profiles.drop_duplicates('CircuitId').iterrows():
        circuit = profile.CircuitId
        layouts = sorted({r['layout_id'] for r in rows if r['circuit_id'] == circuit})
        current = resolve_venue(latest_year, '', circuit_hint=circuit) if circuit in CIRCUITS else {}
        if circuit == 'albert_park':
            current['layout_id'] = 'albert_park_since_2022'
        if current.get('layout_id') and current['layout_id'] not in layouts:
            layouts.append(current['layout_id'])
        for layout in layouts or [None]:
            local = [r for r in rows if r['layout_id'] == layout] if layout else []
            sc, red = (posterior(rows, layout, m) for m in DEFAULTS)
            candidates.append({'circuit_id': circuit, 'circuit_name': profile.CircuitName,
                'layout_id': layout, 'current_registry_layout': current.get('layout_id') == layout if layout else False,
                'reference_last_season': profile.LastSeason,
                'profile_status': profile.ProfileStatus, 'candidate_status':
                    'estimated_inactive' if sc['races'] else 'insufficient_data',
                'observed_seasons': sorted({r['year'] for r in local}),
                'safety_car': sc if sc['races'] else None, 'red_flag': red if red['races'] else None,
                'order_change_proxy': proxy_posterior(rows, layout),
                'active_overtaking_difficulty': float(profile.OvertakingDifficulty),
                'candidate_overtaking_difficulty': None,
                'difficulty_status': 'requires_simulation_parameter_fit',
                'active_safety_car': active[circuit, 'safety_car'], 'active_red_flag': active[circuit, 'red_flag']})
    return {'schema_version': 1, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'workspace': str(Path(workspace).resolve()), 'years': years, 'active': False,
        'profile_source': str(Path(profiles_path).resolve()), 'profile_sha256': sha256(profiles_path),
        'method': {'event_window': 'first lap start to first finish at maximum completed lap; initial step state included',
            'safety_car_code': '4 only; VSC 6/7 separate', 'red_flag_code': '5',
            'prior_races': PRIOR_RACES, 'interval': '90% marginal Bayesian credible interval',
            'pooled_prior': 'earlier races with four default-centred pseudo-races; layout strength four races',
            'proxy': 'nearby adjacent same-lap crossing-order reversals; four clean green driver-laps; gaps <=15s; lap >=3',
            'proxy_prior_pair_laps': PROXY_PRIOR_EXPOSURE,
            'layout_policy': 'saved physical identity plus explicit Yas Island alias; Melbourne split at 2022; saved Barcelona/Singapore splits retained'},
        'coverage': {'included_races': len(rows), 'excluded_races': len(excluded),
            'circuits_with_observations': len({r['circuit_id'] for r in rows}),
            'event_observations': sum(r['events'] is not None for r in rows),
            'proxy_observations': sum(r['order_change_proxy']['changes'] is not None for r in rows),
            'session_status_available': sum(r['session_status_available'] for r in rows),
            'excluded_reasons': dict(Counter(r['reason'] for r in excluded))},
        'promotion': {'eligible': False, 'reasons': [
            'Historical races already inspected: all comparisons are diagnostic, not fresh validation.',
            'Overtaking difficulty is a simulation grid-loss coefficient; timing proxy does not identify its value.',
            'Event-rate scoring does not establish improved full-race finishing predictions.',
            'Few races per layout; changing weather, regulations and race length are not modelled.']},
        'limitations': ['Green timing reversals are not verified overtakes; lapping and within-lap reversals remain limitations.',
            'Proxy intervals condition on independent pair-lap counts and a fixed pooled prior; serial dependence and between-race variation can make them too narrow.',
            'Red-flag event frequency is not interchangeable with the simulation base parameter before weather/race-control adjustments.',
            'No-data circuits keep explicit missing candidate values, not invented estimates.',
            'Race windows derive from lap timing; most older archives lack raw session-status tables.',
            'Raw status feed completeness is assumed from completed archive; no independent event audit.',
            'Layout registry does not encode every resurfacing, corner modification or DRS change.'],
        'candidates': candidates, 'observations': rows, 'excluded': excluded,
        'benchmark_scores': scores, 'benchmark_predictions': predictions}


def render_report(report):
    def escape(value):
        return html.escape(str(value))
    def estimate(value):
        if value is None:
            return 'No evidence'
        return f"{value['mean']:.0%} ({value['low90']:.0%}–{value['high90']:.0%}); {value['events']}/{value['races']} races"
    rows = []
    for item in sorted(report['candidates'], key=lambda r: (r['candidate_status'] != 'estimated_inactive', r['circuit_name'], str(r['layout_id']))):
        proxy = item['order_change_proxy']
        text = ('No evidence' if proxy['mean_per_1000'] is None else
            f"{proxy['mean_per_1000']:.1f} ({proxy['low90_per_1000']:.1f}–{proxy['high90_per_1000']:.1f}); "
            f"{proxy['changes']}/{proxy['exposure']} pair-laps")
        cells = [item['circuit_name'], item['layout_id'] or 'Unobserved', item['candidate_status'],
            ', '.join(map(str, item['observed_seasons'])) or 'None', estimate(item['safety_car']),
            estimate(item['red_flag']), text, f"{item['active_overtaking_difficulty']:.2f} active; candidate unfitted"]
        rows.append('<tr>'+''.join(f'<td>{escape(v)}</td>' for v in cells)+'</tr>')
    scores = pd.DataFrame(report['benchmark_scores']).round(5).to_html(index=False, border=0)
    excluded = ''.join(f"<li>{escape(r['year'])} {escape(r['event'])}: {escape(r['reason'])}</li>" for r in report['excluded'])
    limits = ''.join(f'<li>{escape(v)}</li>' for v in report['promotion']['reasons']+report['limitations'])
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Circuit evidence — inactive candidate</title>
<style>body{{background:#191d28;color:#e6edf3;font:15px system-ui;margin:32px}}h1,h2{{color:#b9e9ef}}p{{max-width:1000px;line-height:1.6}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #3e4658}}thead{{background:#282e3d}}li{{margin:8px 0}}.badge{{color:#ffc878}}.scroll{{overflow:auto}}</style>
<h1>Circuit evidence <span class="badge">· Inactive candidate</span></h1>
<p>Created {escape(report['created_at_utc'])}. {report['coverage']['included_races']} races,
{report['coverage']['circuits_with_observations']} observed circuits; {report['coverage']['excluded_races']} excluded.
Live profiles and forecasts are unchanged. Intervals show 90% marginal uncertainty, conditional on the declared model.</p>
<p>Safety car means a full SC (VSC excluded). Rates use four races of shrinkage toward the pooled rate.
The order-change proxy counts nearby adjacent reversals over two clean green laps; it is not an official overtake count.
The simulation difficulty coefficient still requires a separate fit and finishing-order benchmark.</p>
<div class="scroll"><table><thead><tr><th>Circuit</th><th>Layout regime</th><th>Evidence status</th><th>Seasons</th><th>Safety car: mean (90%); observed</th><th>Red flag: mean (90%); observed</th><th>Order changes per 1,000 pair-laps (90%); observed</th><th>Simulation difficulty</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2>Chronological diagnostic benchmark</h2><p>Each prediction uses only earlier year/round observations. Scoring starts in 2022.
The 2026 comparison updates after each race; it is a rolling diagnostic, not an untouched holdout.
Lower Brier and log loss are better. These scores assess event probabilities, not finishing positions.</p>{scores}
<h2>Activation blocked</h2><ul>{limits}</ul><h2>Excluded archives</h2><ul>{excluded}</ul></html>'''
