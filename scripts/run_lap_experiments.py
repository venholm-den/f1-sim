"""Prepare a Simulink scenario batch or verify its completed outputs.

No downloads or changes to production prediction outputs. All scenarios use
the same existing feature snapshot and intentionally simplified dynamics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.simulink_export import build_simulink_inputs, _evenly_spaced_pit_laps


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_laps(case: pd.Series) -> pd.DataFrame:
    """Independent vector calculation: tyre age = lap minus latest completed pit.

    A pit on lap p adds cost on p and installs fresh tyres for p+1.
    """
    n = int(case.race_laps)
    laps = np.arange(1, n + 1)
    text = str(case.pit_laps) if pd.notna(case.pit_laps) else ''
    pits = np.array([int(v) for v in text.split(';') if v], dtype=int)
    age = laps - 1 + float(case.initial_tyre_age_laps)
    for pit in pits:
        age = np.where(laps > pit, laps - pit - 1, age)
    fuel = np.maximum(0, case.initial_fuel_penalty_seconds - (laps - 1)*case.fuel_gain_per_lap_seconds)
    pit_cost = np.isin(laps, pits) * case.pit_loss_seconds
    lap_time = case.base_lap_time_seconds + case.pace_offset_seconds + age*case.tyre_degradation_seconds_per_lap + fuel + pit_cost
    return pd.DataFrame({'lap': laps, 'lap_time_seconds': lap_time,
                         'cumulative_time_seconds': np.cumsum(lap_time),
                         'tyre_age_laps': age, 'fuel_penalty_seconds': fuel,
                         'pit_penalty_seconds': pit_cost})


def prepare(features: Path, strategies: Path, output: Path) -> None:
    baseline = build_simulink_inputs(pd.read_csv(features), pd.read_csv(strategies))
    if baseline.race_laps.iloc[0] < 8:
        raise ValueError('The scenario batch needs at least eight laps.')
    variants = {'baseline': baseline.copy()}
    for stops in range(4):
        frame = baseline.copy()
        frame['expected_stops'] = stops
        frame['pit_laps'] = [_evenly_spaced_pit_laps(int(n), stops) for n in frame.race_laps]
        variants[f'stops_{stops}'] = frame
    for name, shift in [('pit_early_5', -5), ('pit_late_5', 5)]:
        frame = baseline.copy()
        schedules = []
        for row in frame.itertuples():
            pits = [int(v) for v in str(row.pit_laps).split(';') if v]
            # Bound the common shift to preserve spacing and stop count.
            delta = max(1-pits[0], min(shift, row.race_laps-1-pits[-1])) if pits else 0
            schedules.append(';'.join(str(p+delta) for p in pits))
        frame['pit_laps'] = schedules
        variants[name] = frame
    for name, factor in [('degradation_low', .75), ('degradation_high', 1.25)]:
        frame = baseline.copy()
        frame['tyre_degradation_seconds_per_lap'] *= factor
        variants[name] = frame
    for name, delta in [('pit_loss_low', -5), ('pit_loss_high', 5)]:
        frame = baseline.copy()
        frame['pit_loss_seconds'] = np.maximum(0, frame.pit_loss_seconds + delta)
        variants[name] = frame
    frames = []
    for scenario, frame in variants.items():
        frame['scenario'] = scenario
        frame['case_id'] = frame.Driver + '__' + scenario
        frames.append(frame)
    cases = pd.concat(frames, ignore_index=True)
    output.mkdir(parents=True, exist_ok=True)
    inputs = output / 'experiment_inputs.csv'
    cases.to_csv(inputs, index=False)
    manifest = {'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'classification': 'UNVALIDATED_SCENARIO_EXPERIMENT',
                'case_count': len(cases), 'driver_count': len(baseline),
                'scenarios': list(variants), 'inputs_sha256': sha256(inputs),
                'sources': [{'path': str(p.resolve()), 'sha256': sha256(p)} for p in [features, strategies]],
                'limitations': ['Existing local snapshot; no new event data fetched.',
                                'Constant degradation across compounds; no traffic, DNF, weather or safety car.',
                                'Zero stops is a diagnostic, not a dry-race strategy recommendation.',
                                'Fuel and pit defaults are assumptions; simulated times are not calibrated race forecasts.']}
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Prepared {len(cases)} cases, {len(baseline)} drivers, {len(variants)} scenarios: {inputs}')


def verify(output: Path) -> None:
    inputs = output/'experiment_inputs.csv'
    manifest = json.loads((output/'manifest.json').read_text(encoding='utf-8'))
    if sha256(inputs) != manifest['inputs_sha256']:
        raise ValueError('Experiment inputs changed after preparation; prepare and simulate again.')
    cases = pd.read_csv(inputs, dtype={'pit_laps': str}, keep_default_na=False)
    detail_path = output/'lap_dynamics_results.csv'
    summary_path = output/'lap_dynamics_summary.csv'
    detail = pd.read_csv(detail_path)
    summary = pd.read_csv(summary_path)
    expected_ids = set(cases.case_id)
    if set(detail.case_id) != expected_ids or set(summary.case_id) != expected_ids or summary.case_id.duplicated().any():
        raise ValueError('Missing or duplicated simulation cases.')
    errors = []
    columns = ['lap_time_seconds', 'cumulative_time_seconds', 'tyre_age_laps', 'fuel_penalty_seconds', 'pit_penalty_seconds']
    for _, case in cases.iterrows():
        actual = detail[detail.case_id.eq(case.case_id)].sort_values('lap')
        expected = reference_laps(case)
        if len(actual) != len(expected) or actual.lap.tolist() != expected.lap.tolist():
            raise ValueError(f'Missing or duplicate laps for {case.case_id}')
        if not np.allclose(actual[columns], expected[columns], rtol=0, atol=1e-8):
            raise ValueError(f'Analytical reference mismatch for {case.case_id}')
        result = summary[summary.case_id.eq(case.case_id)].iloc[0]
        if result.pit_stops != case.expected_stops or not np.isclose(result.simulated_race_time_seconds, expected.cumulative_time_seconds.iloc[-1], rtol=0, atol=1e-8):
            raise ValueError(f'Summary mismatch for {case.case_id}')
        errors.append(float(np.max(np.abs(actual[columns].to_numpy()-expected[columns].to_numpy()))))
    comparison = summary.merge(cases[['case_id','expected_stops','pit_laps', 'tyre_degradation_seconds_per_lap','pit_loss_seconds']], on='case_id', validate='one_to_one')
    baseline = comparison[comparison.scenario.eq('baseline')].set_index('Driver').simulated_race_time_seconds
    comparison['delta_vs_baseline_seconds'] = comparison.simulated_race_time_seconds - comparison.Driver.map(baseline)
    comparison.sort_values(['Driver','scenario']).to_csv(output/'scenario_comparison.csv', index=False)
    aggregates = comparison.groupby('scenario').delta_vs_baseline_seconds.agg(['min','median','max'])
    aggregates.to_csv(output/'scenario_effects.csv')
    audit = {'verified_at_utc': datetime.now(timezone.utc).isoformat(), 'cases_verified': len(cases),
             'laps_verified': len(detail), 'max_absolute_error': max(errors),
             'tolerance': 1e-8, 'status': 'PASS',
             'inputs_sha256': sha256(inputs), 'detail_sha256': sha256(detail_path),
             'summary_sha256': sha256(summary_path)}
    (output/'verification.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    lines = ['# Simulink scenario results', '', f'Verified {len(cases)} cases and {len(detail)} laps against an independent Python calculation.',
             f'Maximum absolute signal error: {max(errors):.3g}; tolerance: 1e-8.', '',
             'Time changes versus the same driver baseline; negative means faster under these assumptions.', '',
             '| Scenario | Min (s) | Median (s) | Max (s) |','| --- | ---: | ---: | ---: |']
    for scenario, row in aggregates.iterrows():
        lines.append(f'| {scenario} | {row["min"]:.3f} | {row["median"]:.3f} | {row["max"]:.3f} |')
    lines += ['', '## Interpretation limits', ''] + [f'- {v}' for v in manifest['limitations']]
    lines += ['', 'Sources and checksums are recorded in manifest.json; verification.json records the exact output hashes.']
    (output/'results.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(audit, indent=2))
    print(aggregates.to_string())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare','verify'])
    parser.add_argument('--features', type=Path, default=Path('outputs/driver_model_features.csv'))
    parser.add_argument('--strategies', type=Path, default=Path('outputs/strategy/predicted_tyre_strategy.csv'))
    parser.add_argument('--output-dir', type=Path, default=Path('outputs/matlab/experiments'))
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.features, args.strategies, args.output_dir)
    else:
        verify(args.output_dir)
