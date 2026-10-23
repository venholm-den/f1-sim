"""Measured Discord summaries and readable charts derived from frozen tables."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.app_services.beta import digest, verified_snapshot
from src.discord_post import validate_message


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _text(value) -> str:
    # Keep identifiers legible without treating source text as Discord markup.
    return str(value).replace('@', '@\u200b').replace('`', '').replace('*', '').replace('\n', ' ')[:100]


def _number(value, decimals=2) -> str:
    try:
        return f'{float(value):.{decimals}f}' if math.isfinite(float(value)) else 'unavailable'
    except (TypeError, ValueError):
        return 'unavailable'


def _probability(value) -> str:
    try:
        value = float(value)
        return f'{value:.1%}' if math.isfinite(value) and 0 <= value <= 1 else 'unavailable'
    except (TypeError, ValueError):
        return 'unavailable'


def _field(name, value, inline=False):
    return {'name': name, 'value': str(value), 'inline': inline}


def _previous_forecast(folder: Path, manifest: dict) -> tuple[dict, pd.DataFrame] | None:
    candidates = []
    context = manifest['context']
    created = datetime.fromisoformat(manifest['created_at_utc'])
    for path in folder.parent.glob('*/job.json'):
        job = read_json(path)
        if path.parent == folder or job.get('kind') != 'forecast' or job.get('status') != 'completed':
            continue
        try:
            previous = verified_snapshot(path.parent)
            saved = previous['context']
            timestamp = datetime.fromisoformat(previous['created_at_utc'])
            if (saved['year'] == context['year'] and saved['event'] == context['event']
                    and timestamp < created
                    and previous['category'] == manifest['category']):
                candidates.append((timestamp, path.parent, previous))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    if not candidates:
        return None
    superseded = context.get('supersedes_forecast')
    if superseded:
        candidates = [item for item in candidates if item[1].name == superseded]
        if not candidates:
            return None
    _, source, previous = max(candidates, key=lambda item: item[0])
    return previous, pd.read_csv(source / 'frozen/simulation_summary.csv')


def forecast_changes(folder: Path, manifest: dict, summary: pd.DataFrame) -> str:
    previous = _previous_forecast(folder, manifest)
    if previous is None:
        return 'First available frozen forecast for this race; session comparison unavailable.'
    saved, earlier = previous
    label = _text(saved['context']['session'])
    if saved['context']['session'] == manifest['context']['session']:
        label += ' (previous revision)'
    if (summary.Driver.duplicated().any() or earlier.Driver.duplicated().any()
            or set(summary.Driver) != set(earlier.Driver)):
        return f'Driver roster differs from {label}; like-for-like session changes withheld.'
    data = summary.merge(earlier, on='Driver', suffixes=('', '_previous'), validate='one_to_one')
    lines = [f'Compared with **{label}**:']
    if 'win_chance' in data and 'win_chance_previous' in data:
        delta = (data.win_chance - data.win_chance_previous) * 100
        for index in delta.abs().nlargest(3).index:
            if abs(delta.loc[index]) >= .1:
                lines.append(f"**{_text(data.loc[index, 'Driver'])}** win chance {delta.loc[index]:+.1f} pp")
    if 'avg_finish' in data and 'avg_finish_previous' in data:
        delta = data.avg_finish - data.avg_finish_previous
        for index in delta.abs().nlargest(2).index:
            if abs(delta.loc[index]) >= .05:
                direction = 'better' if delta.loc[index] < 0 else 'worse'
                lines.append(f"**{_text(data.loc[index, 'Driver'])}** average finish {abs(delta.loc[index]):.2f} places {direction}")
    if len(lines) == 1:
        lines.append('No changes above 0.1 percentage points or 0.05 finishing places.')
    lines.append('Descriptive changes; session inputs and model/settings may both contribute.')
    return '\n'.join(lines)


def forecast_message(folder: Path) -> dict:
    manifest = verified_snapshot(folder)
    context = manifest['context']
    summary = pd.read_csv(folder / 'frozen/simulation_summary.csv')
    has_win = 'win_chance' in summary and summary.win_chance.notna().any()
    leaders = summary.sort_values('win_chance' if has_win else 'avg_finish', ascending=not has_win).head(5)
    lines = []
    for row in leaders.to_dict('records'):
        chance = f" • win {_probability(row['win_chance'])}" if has_win else ''
        lines.append(f"**{_text(row['Driver'])}**{chance} • average finish {_number(row['avg_finish'])}")
    job = read_json(folder / 'job.json')
    fields = [
        _field('Forecast inputs', f"**{_text(context['session'])}** • {len(summary)} drivers • "
               f"{int(job.get('n_sims', 10000)):,} simulations"),
        _field('Highest win chances' if has_win else 'Best expected finishes', '\n'.join(lines)),
        _field('Changes since previous forecast', forecast_changes(folder, manifest, summary)),
    ]
    from src.app_services.driver_explanations import build_driver_explanations, rank_text
    explanations = build_driver_explanations(folder)
    if not explanations.empty and explanations.pace_rank.notna().any():
        by_driver = explanations.set_index('Driver')
        for driver in leaders.Driver:
            row = by_driver.loc[driver]
            detail = (f"Projected pace {rank_text(row.pace_rank)}. {row.pace_explanation}\n"
                      f"{row.grid_explanation} {row.retirement_explanation}\n"
                      f"Evidence: {row.evidence_limits}")
            name = f'Why {_text(driver)} has this win chance' if has_win else f'Why {_text(driver)} has this projected finish'
            fields.append(_field(name, detail[:1024]))
        fields.append(_field('How to read these explanations',
            'Blend percentages explain projected pace, not contributions to win probability. '
            'Field normalisation also affects pace ranks. '
            'Full-field chart and reasoning attached. Long-run scores may be derived estimates; '
            'observed matched-run evidence is identified separately.'))
    else:
        fields.append(_field('Driver explanations', 'Verified pace evidence unavailable for this snapshot; no driver-specific causes inferred.'))
    if 'dnf_chance' in summary and summary.dnf_chance.notna().any():
        risks = summary.nlargest(3, 'dnf_chance')
        fields.append(_field('Modelled retirement risk', '\n'.join(
            f"**{_text(row.Driver)}** {_probability(row.dnf_chance)}" for row in risks.itertuples())))
    weather = read_json(folder / 'frozen/race_weather.json') if 'race_weather.json' in manifest['files'] else None
    if weather:
        from src.race_weather import briefing
        weather_time = int(datetime.fromisoformat(weather['retrieved_at_utc']).timestamp())
        fields.append(_field('Race weather and delayed starts', briefing(weather) + f'\nWeather captured <t:{weather_time}:f>.'))
    weather_assumption = ('Weather modifiers use observed session data; race forecast is informational.' if weather
                          else 'Weather modifiers use observed session data; race rain forecast unavailable.')
    venue = context.get('venue', {})
    if venue:
        fields.append(_field('Race venue',
            f"{_text(venue.get('circuit_name') or 'Unresolved circuit')} • {_text(venue.get('venue_country') or 'unknown country')}\n"
            f"Race distance: {venue.get('race_laps') or 'unknown'} laps • {_text(venue.get('venue_status', 'unresolved'))}"))
    assumptions = [weather_assumption,
                   'Tyre strategy and tyre availability are estimates.']
    if venue.get('profile_status') == 'generic_uncalibrated':
        assumptions.append('Circuit-specific calibration unavailable; generic track factors used.')
    if venue and venue.get('venue_status') != 'resolved':
        assumptions.append('Circuit identity uncertain: local weather and circuit history withheld; race distance uses a generic assumption.')
    if context['session'] == 'PRE':
        assumptions.append('Before FP1: previous baseline driver roster is an assumption.')
    if 'fantasy_price' not in summary or summary.fantasy_price.isna().any():
        assumptions.append('Fantasy prices incomplete; value rankings unavailable.')
    fields.append(_field('Data and assumptions', '\n'.join(assumptions)))
    cutoff = context.get('data_cutoff_utc')
    if cutoff:
        timestamp = int(datetime.fromisoformat(cutoff.replace('Z', '+00:00')).timestamp())
        fields.append(_field('Data cutoff', f'<t:{timestamp}:f> • <t:{timestamp}:R>'))
    from src.venues import event_display
    revision = ' • FIA grid update' if context.get('revision_reason') == 'fia_grid_update' else ''
    embed = {'title': f"{context['year']} {_text(event_display(context))} | {_text(context['session'])} forecast{revision}",
             'description': f"{_text(manifest['category']).capitalize()} snapshot • frozen before sharing.",
             'color': 0x168A88, 'fields': fields,
             'footer': {'text': 'Experimental model • frozen locally • probabilities are not guarantees'},
             'timestamp': manifest['created_at_utc']}
    # Preserve room for weather/provenance even with unusually long identifiers.
    explanation_fields = [field for field in fields if field['name'].startswith('Why ')]
    total = (len(embed['title']) + len(embed['description']) + len(embed['footer']['text'])
             + sum(len(field['name']) + len(field['value']) for field in fields))
    excess = max(0, total - 6000)
    for field in sorted(explanation_fields, key=lambda field: len(field['value']), reverse=True):
        if not excess:
            break
        previous = len(field['value'])
        keep = max(100, previous - excess)
        suffix = '… Full reasoning attached.'
        field['value'] = field['value'][:keep - len(suffix)].rsplit(' ', 1)[0] + suffix
        excess = max(0, excess - (previous - len(field['value'])))
    payload = {'content': '', 'embeds': [embed]}
    validate_message(**payload)
    return payload


def grid_baseline(comparison: pd.DataFrame) -> float | None:
    """Compare on identical coverage using the positions frozen before the race."""
    if 'grid_position' not in comparison or comparison.empty:
        return None
    grid = pd.to_numeric(comparison.grid_position, errors='coerce')
    if (grid.isna().any() or grid.duplicated().any() or not grid.between(1, len(grid)).all()
            or not grid.eq(grid.round()).all()):
        return None
    return float((grid - comparison.actual_position).abs().mean())


def _retirements(comparison: pd.DataFrame) -> pd.Series | None:
    if 'actual_dnf' not in comparison:
        return None
    values = comparison.actual_dnf.astype(str).str.lower()
    labels = values.map({'true': True, 'false': False, '1': True, '0': False,
                         '1.0': True, '0.0': False}).astype('boolean')
    return labels if labels.notna().any() else None


def analysis_summary(comparison: pd.DataFrame) -> dict:
    result = {'drivers': len(comparison),
              'finish_mae': float((comparison.avg_finish - comparison.actual_position).abs().mean()),
              'grid_baseline_mae': grid_baseline(comparison)}
    retired = _retirements(comparison)
    if retired is not None:
        result['retirements'] = int(retired.sum())
        result['unknown_retirement_labels'] = int(retired.isna().sum())
        survivors = comparison.loc[~retired]
        result['non_retirements'] = len(survivors)
        result['non_retirement_finish_mae'] = (float((survivors.avg_finish - survivors.actual_position).abs().mean())
                                               if len(survivors) else None)
    return result


def _recent_scores(folder: Path, context: dict, current: dict, history_root: Path | None = None) -> str:
    # A small descriptive trend, restricted to verified prospective score jobs.
    rows = []
    seen = {(int(context['year']), context['event'])}
    for path in sorted((history_root or folder.parent).glob('*/job.json'), reverse=True):
        job = read_json(path)
        if job.get('kind') != 'score' or job.get('status') != 'completed':
            continue
        try:
            source = Path(job['forecast_folder'])
            manifest = verified_snapshot(source)
            key = (int(manifest['context']['year']), manifest['context']['event'])
            if context.get('race_start_utc'):
                if pd.Timestamp(manifest['context']['race_start_utc']) > pd.Timestamp(context['race_start_utc']):
                    continue
            metrics = read_json(path.parent / 'score.json')
            if (key in seen or manifest['category'] != 'prospective'
                    or metrics.get('snapshot_sha256') != digest(source / 'frozen/manifest.json')):
                continue
            comparison = pd.read_csv(path.parent / 'score_comparison.csv')
            summary = analysis_summary(comparison)
            if summary['grid_baseline_mae'] is None:
                continue
            seen.add(key)
            rows.append(summary)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if len(rows) == 4:
            break
    if current['grid_baseline_mae'] is None:
        return 'Trend unavailable without a complete frozen grid baseline.'
    rows.insert(0, current)
    if len(rows) == 1:
        return '1 evaluated race with a complete baseline; more races needed for a trend.'
    model = sum(row['finish_mae'] for row in rows) / len(rows)
    grid = sum(row['grid_baseline_mae'] for row in rows) / len(rows)
    wins = sum(row['finish_mae'] < row['grid_baseline_mae'] for row in rows)
    return (f'Last {len(rows)} evaluated races: model **{model:.2f}** vs grid **{grid:.2f}** places.\n'
            f'Model beat baseline in {wins}/{len(rows)} races. Equal weight per race; descriptive only.')


def post_race_message(folder: Path, context: dict, *, history_root: Path | None = None) -> dict:
    comparison = pd.read_csv(folder / 'score_comparison.csv').sort_values('actual_position')
    metrics = read_json(folder / 'score.json')
    summary = analysis_summary(comparison)
    baseline = summary['grid_baseline_mae']
    score = f"Model: **{summary['finish_mae']:.2f} places** mean absolute error."
    if baseline is not None:
        difference = summary['finish_mae'] - baseline
        verdict = 'worse' if difference > .005 else ('better' if difference < -.005 else 'equal')
        score += f'\nFrozen grid baseline: **{baseline:.2f} places**.\nModel {abs(difference):.2f} places {verdict}; lower is better.'
    else:
        score += '\nFrozen grid baseline unavailable: complete grid positions required.'
    podium = '\n'.join(f"P{int(row.actual_position)} **{_text(row.Driver)}** • forecast average {_number(row.avg_finish)}"
                       for row in comparison.head(3).itertuples())
    winner = comparison.iloc[0]
    if 'win_chance' in comparison:
        podium += f"\nWinner's forecast win chance: **{_probability(winner.win_chance)}**."
    missed = comparison.assign(absolute_error=(comparison.avg_finish - comparison.actual_position).abs()).nlargest(3, 'absolute_error')
    lines = []
    retired = _retirements(comparison)
    for index, row in missed.iterrows():
        status = f" • {_text(row.get('actual_status', 'status unavailable'))}"
        if retired is not None and pd.notna(retired.loc[index]) and retired.loc[index]:
            status += f" • forecast DNF {_probability(row.get('dnf_chance'))}"
        lines.append(f"**{_text(row.Driver)}**: average {row.avg_finish:.2f} → P{int(row.actual_position)}{status}")
    fields = [_field('Performance against a simple baseline', score), _field('Actual podium', podium),
              _field('Largest misses and observed outcomes', '\n'.join(lines))]
    if retired is not None:
        retirements = comparison.loc[retired]
        value = f"{len(retirements)}/{int(retired.notna().sum())} drivers with known outcomes retired."
        if retired.isna().any():
            value += f" {int(retired.isna().sum())} retirement outcomes unavailable."
        if len(retirements):
            value += '\n' + '\n'.join(f"**{_text(row.Driver)}** • {_text(getattr(row, 'actual_status', 'Retired'))} • "
                                       f"forecast DNF {_probability(getattr(row, 'dnf_chance', None))}"
                                       for row in retirements.head(5).itertuples())
            if len(retirements) > 5:
                value += f'\n+{len(retirements) - 5} other retirements in the comparison CSV.'
        if summary['non_retirement_finish_mae'] is not None:
            value += (f"\nNon-retirement finish error: {summary['non_retirement_finish_mae']:.2f} places "
                      f"({summary['non_retirements']} drivers; diagnostic subset).")
        fields.append(_field('Retirement context', value))
    brier = []
    for column, label in [('win_chance_brier', 'Win'), ('podium_chance_brier', 'Podium'), ('points_chance_brier', 'Top 10')]:
        if column in metrics:
            brier.append(f'{label} {_number(metrics[column], 4)}')
    if brier:
        fields.append(_field('Probability errors • Brier scores', ' • '.join(brier) + '\nLower is better; single-race scores do not establish calibration.'))
    fields.append(_field('Recent baseline comparison', _recent_scores(folder, context, summary, history_root)))
    from src.venues import event_display
    embed = {'title': f"{context['year']} {_text(event_display(context))} | Post-race analysis",
             'description': f"Official FastF1 results vs frozen **{_text(context['session'])}** forecast • {len(comparison)} drivers.",
             'color': 0xE39B37, 'fields': fields,
             'footer': {'text': 'Grid positions from frozen inputs • observed outcomes do not establish causes'},
             'timestamp': metrics.get('evaluated_at_utc', datetime.now(timezone.utc).isoformat())}
    payload = {'content': '', 'embeds': [embed]}
    validate_message(**payload)
    return payload


def message_text(payload: dict) -> str:
    """Readable local fallback and preview of the same measured embed."""
    lines = [payload.get('content', '')]
    for embed in payload.get('embeds', []):
        lines.extend([f"**{embed['title']}**", embed.get('description', '')])
        for field in embed['fields']:
            lines.extend(['', f"**{field['name']}**", field['value']])
        lines.extend(['', embed['footer']['text']])
    return '\n'.join(lines).strip()


def _plotting():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    return plt


def render_forecast_charts(folder: Path, destination: Path) -> list[Path]:
    verified_snapshot(folder)
    data = pd.read_csv(folder / 'frozen/simulation_summary.csv')
    destination.mkdir(parents=True, exist_ok=True)
    plt = _plotting()
    has_win = 'win_chance' in data and data.win_chance.notna().any()
    leaders = data.sort_values('win_chance' if has_win else 'avg_finish', ascending=not has_win).head(8)
    with plt.rc_context({'font.size': 13}):
        figure, axes = plt.subplots(figsize=(7, 6.5))
        values = leaders.win_chance * 100 if has_win else leaders.avg_finish
        axes.barh(leaders.Driver, values, color='#168a88', height=.65)
        axes.invert_yaxis()
        for index, value in enumerate(values):
            axes.text(value + max(values.max() * .02, .1), index, f'{value:.1f}%' if has_win else f'{value:.2f}', va='center')
        axes.set_xlim(0, max(float(values.max()) * 1.3, 1))
        axes.set(xlabel='Modelled win chance (%)' if has_win else 'Expected finishing position',
                 title='Leading contenders' if has_win else 'Best expected finishes')
        axes.spines[['top', 'right']].set_visible(False)
        figure.text(.5, .015, 'Experimental forecast • probabilities are not guarantees', ha='center', fontsize=10)
        figure.tight_layout(rect=(0, .04, 1, 1))
        outlook = destination / 'forecast_outlook.png'
        figure.savefig(outlook, dpi=170)
        plt.close(figure)

        leaders = data.nsmallest(10, 'avg_finish')
        figure, axes = plt.subplots(figsize=(7, 7))
        ranges = {'finish_p25', 'finish_p75'}.issubset(leaders.columns)
        for index, row in enumerate(leaders.itertuples()):
            if ranges and pd.notna(row.finish_p25) and pd.notna(row.finish_p75):
                axes.plot([row.finish_p25, row.finish_p75], [index, index], color='#b8dcd9', linewidth=8, solid_capstyle='round')
            axes.scatter(row.avg_finish, index, color='#168a88', s=70, zorder=3)
        axes.set_yticks(range(len(leaders)), leaders.Driver)
        axes.invert_yaxis()
        axes.set_xticks(range(1, len(data) + 1, 2))
        axes.set_xlim(.5, len(data) + .5)
        axes.set(xlabel='Finishing position', title='Expected finish and outcome range')
        axes.grid(axis='x', alpha=.15)
        axes.spines[['top', 'right']].set_visible(False)
        caption = 'Dot: average • line: middle 50% of simulated finishes' if ranges else 'Dot: average • simulation ranges unavailable'
        figure.text(.5, .025, caption, ha='center', fontsize=10)
        figure.tight_layout(rect=(0, .05, 1, 1))
        finish = destination / 'finish_ranges.png'
        figure.savefig(finish, dpi=170)
        plt.close(figure)
    return [outlook, finish]
