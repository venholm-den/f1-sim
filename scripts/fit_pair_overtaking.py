"""Fit the pair_overtaking_v1 pass model from a recent-baseline packet.

Reads the packet's race laps (2026 only, so no DRS) and the calibrated track
difficulties, writes the coefficients as JSON and, optionally, the pair-lap
table. Also prints a rolling earlier-races-only log-loss comparison against a
constant and a track-only (single factor) model. Writes new files only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.pair_overtaking import FEATURES, build_dataset, fit_logistic, fit_model, predict

DEFAULT_PACKET = 'data/recent_baselines/singapore-20261005-v4-venues'
DEFAULT_CALIBRATION = 'data/track_calibration/track_calibration_v1.csv'


def _log_loss(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(np.mean(-(y * np.log(p) + (1 - y) * np.log(1 - p))))


def rolling_comparison(data, first_round=4):
    """Score each round with models fitted on earlier rounds only."""
    rows = []
    for round_ in sorted(r for r in data['round'].unique() if r >= first_round):
        train, test = data[data['round'] < round_], data[data['round'] == round_]
        track, _ = fit_logistic(train, columns=('track',))
        pair, _ = fit_logistic(train)
        rows.append({'round': int(round_), 'event': test.event.iloc[0], 'pair_laps': len(test),
                     'passes': int(test.passed.sum()),
                     'constant': _log_loss(test.passed, np.full(len(test), train.passed.mean())),
                     'track_only': _log_loss(test.passed, predict(test, track, ('track',))),
                     'pair': _log_loss(test.passed, predict(test, pair, FEATURES))})
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', default=DEFAULT_PACKET)
    parser.add_argument('--calibration', default=DEFAULT_CALIBRATION)
    parser.add_argument('--output', required=True)
    parser.add_argument('--save-pairs')
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise SystemExit(f'Refusing to overwrite {output}.')
    laps_path = Path(args.packet) / 'fastf1_laps.csv'
    laps = pd.read_csv(laps_path)
    if laps.Year.lt(2026).any():
        raise SystemExit('Pair model is fitted on 2026+ races only (no DRS).')
    data = build_dataset(laps, pd.read_csv(args.calibration))
    model = fit_model(data)
    model['sources'] = {str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest()
                        for p in (laps_path, Path(args.calibration))}
    comparison = rolling_comparison(data)
    weights = comparison.pair_laps / comparison.pair_laps.sum()
    model['rolling_log_loss'] = {k: float((comparison[k] * weights).sum())
                                 for k in ('constant', 'track_only', 'pair')}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(model, indent=2) + '\n', encoding='utf-8')
    if args.save_pairs:
        data.to_csv(args.save_pairs, index=False)
    print(comparison.round(4).to_string(index=False))
    print(json.dumps({k: model[k] for k in ('intercept', 'pace', 'tyre_age', 'compound', 'track',
                                            'pair_laps', 'passes', 'rolling_log_loss')}, indent=2))
    print(f'saved: {output}')


if __name__ == '__main__':
    main()
