"""Driver explanations from verified forecast inputs, without rerunning the model."""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from src.app_services.beta import verified_snapshot


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def label(value):
    return str(value).replace('@', '@\u200b').replace('`', '').replace('*', '').replace('\n', ' ')[:100]


def rank_text(value):
    value = number(value)
    return f'#{int(value)}' if value is not None else 'unavailable'


def _rank(frame, column):
    values = pd.to_numeric(frame.get(column, pd.Series(index=frame.index, dtype=float)), errors='coerce')
    return values.where(values.map(lambda value: pd.notna(value) and math.isfinite(value))).rank(method='min')


def _history(baseline, driver):
    required = {'Driver', 'source_year', 'source_event', 'source_round', 'baseline_age', 'relative_pace'}
    if baseline.empty or not required.issubset(baseline):
        return 'Race identities unavailable in this frozen snapshot.'
    rows = baseline.loc[baseline.Driver.eq(driver)].copy()
    rows = rows.loc[pd.to_numeric(rows.relative_pace, errors='coerce').notna()]
    if rows.empty:
        return 'No usable historical pace rows.'
    keys = ['source_year', 'source_round']
    if rows.duplicated(keys).any():
        return 'Historical race identities ambiguous; details withheld.'
    all_rows = baseline.copy()
    all_rows['race_rank'] = all_rows.groupby(keys).relative_pace.transform(
        lambda values: pd.to_numeric(values, errors='coerce').rank(method='min'))
    rows = rows.join(all_rows['race_rank'])
    rows = rows.sort_values('baseline_age')
    weights = pd.to_numeric(rows.baseline_age, errors='coerce')
    if weights.isna().any() or weights.lt(0).any():
        return 'Historical recency weights unavailable.'
    weights = 1 / (1 + weights * .45)
    weights = weights / weights.sum()
    descriptions = []
    for index, row in rows.iterrows():
        circuit = f", circuit {label(row.source_circuit_id)}" if 'source_circuit_id' in row and pd.notna(row.source_circuit_id) else ''
        laps = number(row.get('clean_laps'))
        coverage = f", {int(laps)} usable laps" if laps is not None else ''
        descriptions.append(f"{label(row.source_year)} {label(row.source_event)} (round {label(row.source_round)}): "
                            f"pace {rank_text(row.race_rank)}, {weights.loc[index]:.1%} of historical blend{coverage}{circuit}")
    return '; '.join(descriptions) + '. Ranks use that historical race field; different circuits are not direct lap-time comparisons.'


def build_driver_explanations(folder: Path) -> pd.DataFrame:
    """Only manifest-listed, checksum-verified files may support a claim."""
    manifest = verified_snapshot(folder)
    summary = pd.read_csv(folder / 'frozen/simulation_summary.csv')
    if 'features.csv' not in manifest['files']:
        return pd.DataFrame()
    try:
        features = pd.read_csv(folder / 'frozen/features.csv')
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    if ('Driver' not in features or features.Driver.duplicated().any()
            or summary.Driver.duplicated().any() or set(features.Driver) != set(summary.Driver)):
        return pd.DataFrame()
    # Summary probabilities are authoritative; explanation inputs come from features.
    data = features.drop(columns=[c for c in ('win_chance', 'dnf_chance', 'avg_finish') if c in features]).merge(
        summary[['Driver', *[c for c in ('win_chance', 'dnf_chance', 'avg_finish') if c in summary]]],
        on='Driver', validate='one_to_one')
    for name, column in [('pace_rank', 'race_pace_score'), ('baseline_rank', 'baseline_relative_pace'),
                         ('session_rank', 'current_relative_pace_capped')]:
        data[name] = _rank(data, column)
    try:
        baseline = (pd.read_csv(folder / 'frozen/baseline_race_features.csv')
                    if 'baseline_race_features.csv' in manifest['files'] else pd.DataFrame())
    except pd.errors.EmptyDataError:
        baseline = pd.DataFrame()
    session = label(manifest['context']['session'])
    rows = []
    for record in data.to_dict('records'):
        get = lambda key: number(record.get(key))
        model = str(record.get('performance_model_version', ''))
        rounds, laps = get('baseline_rounds'), get('clean_laps')
        baseline_rank, current_rank = record['baseline_rank'], record['session_rank']
        why = []
        limits = []
        share = None
        calibration = get('historical_finish_weight')
        if model == 'phase_1_performance_profile' and not (calibration is not None and calibration > 0):
            effective, race_weight = get('effective_current_weight'), get('race_weight_used')
            if (effective is not None and race_weight is not None
                    and 0 <= effective <= 1 and 0 <= race_weight <= 1
                    and get('baseline_relative_pace') is not None):
                share = effective * race_weight
                why.append(f'Pace input weights: {1 - share:.1%} recent-race history / {share:.1%} {session} evidence.')
            else:
                limits.append('Effective blend unavailable; missing inputs or fallback path.')
            if get('baseline_relative_pace') is not None:
                why.append(f'Historical pace {rank_text(baseline_rank)} among the current drivers' +
                           (f' across {int(rounds)} races.' if rounds is not None else '; race count unavailable.'))
            if session != 'PRE' and get('current_relative_pace_capped') is not None:
                why.append(f'{session} pace {rank_text(current_rank)} after model caps' +
                           (f', using {int(laps)} usable laps.' if laps is not None else '; lap count unavailable.'))
            if number(baseline_rank) is not None and number(current_rank) is not None and session != 'PRE':
                if baseline_rank < current_rank:
                    why.append('History ranks stronger than the current session.')
                elif baseline_rank > current_rank:
                    why.append('Current session ranks stronger than history.')
            long_run = 'Long-run score is derived from pace, degradation and lap variability; not a measured sustained-run estimate.'
        elif model == 'matched_stints_v2' and not (calibration is not None and calibration > 0):
            share, long_laps = get('matched_long_run_weight'), get('long_run_laps')
            if share is not None and 0 <= share <= 1 and get('baseline_relative_pace') is not None:
                why.append(f'Effective pace blend: {1 - share:.1%} history / {share:.1%} matched practice runs.')
            else:
                share = None
                limits.append('Matched-run blend unavailable.')
            why.append(f'Historical pace {rank_text(baseline_rank)} among the current drivers.')
            long_run = (f'Matched practice-run evidence: {int(long_laps)} laps. ' if long_laps is not None else '') + 'Fuel load remains unknown; this is not a pure tyre-wear or fuel-corrected estimate.'
        else:
            why.append('Pace blend unavailable for this model version or active historical calibration.')
            long_run = 'Sustained-run evidence not established by this explanation.'
        if rounds is None:
            limits.append('Historical coverage unavailable.')
        elif rounds < 5:
            limits.append(f'Limited history: {int(rounds)} races.')
        if session == 'PRE':
            limits.append('Before FP1: no current-weekend lap evidence.')
        elif laps is not None and laps < 8:
            limits.append(f'Sparse {session} evidence: {int(laps)} usable laps.')
        if session != 'PRE' and get('current_relative_pace') is None:
            limits.append('Current-session pace missing; no observed weekend pace claim.')
        quality = get('current_signal_quality')
        if session != 'PRE' and quality is not None and quality < 1:
            limits.append('Current-session weight reduced for lap coverage/variability/outlier checks.')
        if get('current_relative_pace') != get('current_relative_pace_capped'):
            limits.append('Current pace was capped by the model.')
        grid = get('grid_position')
        source = record.get('grid_source')
        grid_source = {'fia_official_grid': 'FIA official grid', 'actual_session_results': 'session classification; later penalties may differ'}.get(source, 'estimated grid')
        grid_reason = f'P{int(grid)} from {grid_source}.' if grid is not None else 'Grid unavailable.'
        penalty_notes = record.get('fia_penalty_notes')
        if pd.notna(penalty_notes) and str(penalty_notes).strip():
            grid_reason += ' FIA decision: '+str(penalty_notes).strip()+'.'
            if source!='fia_official_grid':
                limits.append('FIA grid sanction recorded; revised official race grid unavailable, so placement is not applied.')
        if grid is not None and grid > 1:
            grid_reason += ' Starting behind pole adds a modelled grid penalty scaled by circuit overtaking difficulty.'
        elif grid == 1:
            grid_reason += ' Pole avoids the modelled grid penalty.'
        risk = get('dnf_chance')
        risk_text = f'Modelled retirement risk {risk:.1%}.' if risk is not None and 0 <= risk <= 1 else 'Retirement risk unavailable.'
        rows.append({'Driver': record['Driver'], 'win_chance': get('win_chance'),
                     'pace_rank': number(record['pace_rank']), 'baseline_rank': number(baseline_rank),
                     'session_rank': number(current_rank), 'current_pace_share': share,
                     'pace_explanation': ' '.join(why), 'grid_explanation': grid_reason,
                     'retirement_explanation': risk_text, 'historical_races': _history(baseline, record['Driver']),
                     'long_run_evidence': long_run, 'evidence_limits': ' '.join(limits) or 'Coverage checks do not establish prediction accuracy.'})
    return pd.DataFrame(rows)


def render_driver_explanations(folder: Path, destination: Path) -> list[Path]:
    data = build_driver_explanations(folder)
    if data.empty or data.pace_rank.isna().all():
        return []
    destination.mkdir(parents=True, exist_ok=True)
    data = data.sort_values('win_chance', ascending=False, na_position='last')
    csv = destination / 'driver_explanations.csv'
    data.to_csv(csv, index=False)
    lines = ['# Why these win chances?', '',
             'Input explanations, not percentage-point attribution to win probability. Ranks are model estimates.',
             'Own-input weights combine both blending stages. Field normalisation also influences final pace ranks; these weights are not independent causal effects. More recent baseline races receive greater weight.',
             'Fuel loads are not known. Pace estimates do not establish that a driver has a faster car or a fuel-corrected advantage.',
             'Simulated variation and retirements also affect wins; a pace rank alone does not determine the probability.',
             'Race weather forecasts and delayed-start scenarios are informational, not applied to these win probabilities.', '']
    for row in data.to_dict('records'):
        probability = f"{row['win_chance']:.1%}" if number(row['win_chance']) is not None else 'unavailable'
        lines.extend([f"## {label(row['Driver'])} — win {probability}; projected pace {rank_text(row['pace_rank'])}",
                      '', row['pace_explanation'], '', row['grid_explanation'], row['retirement_explanation'],
                      '', 'Historical sources: ' + row['historical_races'], '', row['long_run_evidence'],
                      '', 'Evidence limits: ' + row['evidence_limits'], ''])
    markdown = destination / 'driver_explanations.md'
    markdown.write_text('\n'.join(lines), encoding='utf-8')
    from src.app_services.discord_reports import _plotting
    plt = _plotting()
    with plt.rc_context({'font.size': 11}):
        figure, axes = plt.subplots(figsize=(12, max(5, len(data) * .46 + 1.8)))
        axes.axis('off')
        cells = []
        for row in data.to_dict('records'):
            share = number(row['current_pace_share'])
            chance = number(row['win_chance'])
            cells.append([label(row['Driver']), f'{chance:.1%}' if chance is not None else 'unknown',
                          rank_text(row['pace_rank']), rank_text(row['baseline_rank']),
                          rank_text(row['session_rank']),
                          f'{share:.1%}' if share is not None else 'unknown',
                          row['grid_explanation'].split(';')[0].split('.')[0].replace(' from ', ' / '),
                          row['retirement_explanation'].replace('Modelled retirement risk ', '').rstrip('.')])
        table = axes.table(cellText=cells, colLabels=['Driver', 'Win', 'Pace rank', 'History rank', 'Session rank', 'Session/run share', 'Grid source', 'DNF risk'],
                           colWidths=[.07, .07, .08, .10, .10, .13, .35, .10], bbox=[0, .03, 1, .92], cellLoc='left')
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1.65)
        for (row, column), cell in table.get_celld().items():
            cell.set_facecolor('#168a88' if row == 0 else ('#edf5f4' if row % 2 else '#ffffff'))
            if row == 0:
                cell.get_text().set_color('white')
        axes.set_title('Evidence behind each driver\'s win chance', pad=20)
        figure.text(.5, .02, 'Blend shares explain pace, not win %. Classification grids may change after penalties.\nFull reasoning and limitations in driver_explanations.md', ha='center', fontsize=10)
        figure.tight_layout(rect=(0, .05, 1, .98))
        chart = destination / 'driver_explanations.png'
        figure.savefig(chart, dpi=170)
        plt.close(figure)
    return [chart, markdown, csv]
