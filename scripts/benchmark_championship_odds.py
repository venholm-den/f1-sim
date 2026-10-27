"""Backtest championship odds by cutting past seasons after a round.

For every season in the historical library and every cut round, the completed
classifications up to the cut are simulated forward over the sessions that
were actually run afterwards, and compared with what happened:

- points_mae: mean absolute error of each driver's expected remaining points
- title_brier: sum over drivers of (title chance - champion)^2, per cut
- title_log_loss: -log of the eventual champion's title chance (floored at 0.1%)
- top3_brier: as title_brier for finishing the season in the top three
- coverage_80: share of drivers whose final points fall inside P10-P90
- combined: title_brier + top3_brier, the promotion score
- surge_bias: mean (expected - actual) remaining points for drivers who scored
  at least 3 points a race more after the cut than before it

A season still in progress is scored against its latest archived round.
Usage: python -m scripts.benchmark_championship_odds --root <app data root>
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from src.championship_odds import OddsSettings, normalise_results, simulate_championship, standings

ARMS = {
    # The first model: team and driver noise added to the drawn finishing place.
    'established': {'pace_mode': 'places'},
    # Team and driver form drift through each driver's own results (the current default).
    'pool_drift_v1': {'pace_mode': 'pool'},
}
# Tuning seasons; later seasons are reported separately.
FIT_YEARS = (2021, 2022, 2023)
LOG_FLOOR = 1e-3


def library_results(library: Path, year: int) -> pd.DataFrame:
    """Every archived race and sprint classification of one season, read straight from the files."""
    frames = []
    for pointer in sorted((library/str(year)/'detailed').glob('*/session.json')):
        saved = json.loads(pointer.read_text(encoding='utf-8'))
        if saved.get('status') != 'complete' or saved.get('session') not in ('R', 'S'):
            continue
        names = [name for name, info in saved.get('files', {}).items() if info.get('table') == 'results']
        files = [pointer.parent/name.replace('\\', '/') for name in names]
        files = [file for file in files if file.is_file()]
        if files:
            frames.append(normalise_results(pd.read_csv(files[0])))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def cut_rounds(results: pd.DataFrame, first: int = 6, last_gap: int = 1) -> list[int]:
    rounds = sorted(results.loc[results['session'].eq('R'), 'round'].unique())
    return [r for r in rounds if first <= r <= rounds[-1] - last_gap]


def score_cut(results: pd.DataFrame, cut: int, settings: OddsSettings) -> pd.DataFrame:
    before = results[results['round'].le(cut)]
    after = results[results['round'].gt(cut)]
    remaining = [{'round': int(r), 'race': bool(group['session'].eq('R').any()),
                  'sprint': bool(group['session'].eq('S').any())}
                 for r, group in after.groupby('round')]
    payload = simulate_championship(before, remaining, settings)
    final, _ = standings(results)
    final = final.set_index('Driver')
    # The champion on points, wins as the tie-break (as in the simulation).
    order = final.sort_values(['points', 'wins'], ascending=False)
    champion, top3 = order.index[0], set(order.index[:3])
    so_far = standings(before)[0].set_index('Driver')['points']
    races_before = before.loc[before['session'].eq('R'), 'round'].nunique()
    races_after = max(1, after.loc[after['session'].eq('R'), 'round'].nunique())
    rows = []
    for row in payload['drivers']:
        name = row['name']
        now = float(so_far.get(name, 0.0))
        actual_final = float(final['points'].get(name, now))
        rows.append({
            'cut': cut, 'driver': name, 'active': row['active'],
            'remaining_races': races_after,
            'expected_gain': row['expected_points'] - now,
            'actual_gain': actual_final - now,
            'p10': row['points_p10'], 'p90': row['points_p90'], 'actual_final': actual_final,
            'title_chance': row['title_chance'], 'champion': name == champion,
            'top3_chance': row['top3_chance'], 'top3': name in top3,
            'rate_before': now / max(1, races_before),
            'rate_after': (actual_final - now) / races_after,
        })
    return pd.DataFrame(rows)


def season_rows(results: pd.DataFrame, year: int, settings: OddsSettings, cuts=None) -> pd.DataFrame:
    frames = [score_cut(results, cut, settings).assign(year=year) for cut in (cuts or cut_rounds(results))]
    return pd.concat(frames, ignore_index=True)


def summarise(rows: pd.DataFrame) -> dict[str, float]:
    active = rows[rows['active']]
    per_cut = rows.assign(title_sq=(rows['title_chance'] - rows['champion']) ** 2,
                          top3_sq=(rows['top3_chance'] - rows['top3']) ** 2).groupby(['year', 'cut'])
    title_brier, top3_brier = per_cut['title_sq'].sum(), per_cut['top3_sq'].sum()
    champion = rows[rows['champion']]
    surgers = active[active['rate_after'] - active['rate_before'] >= 3.0]
    return {
        'cuts': int(per_cut.ngroups),
        'combined': float(title_brier.mean() + top3_brier.mean()),
        'points_mae': float((active['expected_gain'] - active['actual_gain']).abs().mean()),
        'title_brier': float(title_brier.mean()),
        'title_log_loss': float(-np.log(champion['title_chance'].clip(lower=LOG_FLOOR)).mean()),
        'top3_brier': float(top3_brier.mean()),
        'coverage_80': float(active['actual_final'].between(active['p10'], active['p90']).mean()),
        'surge_bias': float((surgers['expected_gain'] - surgers['actual_gain']).mean()) if len(surgers) else float('nan'),
        'surge_rows': int(len(surgers)),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--root', default='.', help='Folder that holds data/historical_library')
    parser.add_argument('--library', help='The historical_library folder itself (overrides --root)')
    parser.add_argument('--years', type=int, nargs='+', default=[2021, 2022, 2023, 2024, 2025, 2026])
    parser.add_argument('--arms', nargs='+', default=list(ARMS))
    parser.add_argument('--n-sims', type=int, default=10000)
    parser.add_argument('--seeds', type=int, nargs='+', default=[2026])
    parser.add_argument('--out', help='Write per-driver rows to this CSV')
    args = parser.parse_args(argv)
    library = Path(args.library) if args.library else Path(args.root)/'data/historical_library'
    seasons = {year: library_results(library, year) for year in args.years}
    seasons = {year: frame for year, frame in seasons.items() if not frame.empty}
    all_rows, report = [], {}
    for arm in args.arms:
        for seed in args.seeds:
            settings = replace(OddsSettings(), n_sims=args.n_sims, seed=seed, **ARMS[arm])
            rows = pd.concat([season_rows(frame, year, settings) for year, frame in seasons.items()],
                             ignore_index=True)
            fit = rows['year'].isin(FIT_YEARS)
            report[f'{arm}@{seed}'] = {'fit': summarise(rows[fit]), 'later': summarise(rows[~fit]),
                                       'all': summarise(rows),
                                       **{str(y): summarise(g) for y, g in rows.groupby('year')}}
            all_rows.append(rows.assign(arm=arm, seed=seed))
    print(json.dumps(report, indent=2))
    if args.out:
        pd.concat(all_rows, ignore_index=True).to_csv(args.out, index=False)
    return report


if __name__ == '__main__':
    main()
