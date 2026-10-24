"""Season form per driver and team-mate head-to-heads, from archived classifications only."""
from __future__ import annotations

import pandas as pd


def season_summary(results: pd.DataFrame) -> dict:
    """Driver season lines and team-mate race head-to-heads.

    results uses the normalise_results schema (round, session, Driver, Team,
    position, points, classified). Points count races and sprints; the other
    figures count Grands Prix only. A head-to-head counts races where both
    team-mates were classified, so a retirement is not scored as being beaten.
    """
    if results.empty:
        return {'rounds': 0, 'drivers': [], 'pairs': []}
    races = results[results['session'].eq('R')]
    latest_team = results.sort_values('round').groupby('Driver')['Team'].last()
    drivers = []
    for driver, group in races.groupby('Driver'):
        finished = group['position'].dropna()
        drivers.append({
            'driver': driver, 'team': latest_team.get(driver, ''),
            'races': int(len(group)), 'wins': int(finished.eq(1).sum()), 'podiums': int(finished.le(3).sum()),
            'points': float(results.loc[results['Driver'].eq(driver), 'points'].sum()),
            'avg_finish': float(finished.mean()) if len(finished) else None,
            'best_finish': int(finished.min()) if len(finished) else None,
            'retirements': int((~group['classified']).sum()),
        })
    drivers.sort(key=lambda row: (-row['points'], row['avg_finish'] if row['avg_finish'] is not None else 99))

    tally = {}
    for (_, team), group in races.groupby(['round', 'Team']):
        if len(group) != 2:
            continue
        a, b = sorted(group.itertuples(index=False), key=lambda row: row.Driver)
        pair = tally.setdefault((team, a.Driver, b.Driver), {'team': team, 'a': a.Driver, 'b': b.Driver,
                                                              'a_ahead': 0, 'b_ahead': 0, 'races': 0})
        pair['races'] += 1
        if a.classified and b.classified:
            pair['a_ahead' if a.position < b.position else 'b_ahead'] += 1
    pairs = sorted(tally.values(), key=lambda pair: (pair['team'], -pair['races']))
    return {'rounds': int(races['round'].nunique()), 'drivers': drivers, 'pairs': pairs}


def driver_intel(root, year) -> dict:
    from src.app_services.championship import archived_results
    year = int(year)
    results = archived_results(root, year)
    if results.empty:
        raise ValueError(f'No {year} race results are downloaded. Download the season in Historical data first.')
    return {'year': year, **season_summary(results)}
