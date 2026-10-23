import json

import pandas as pd
import pytest

from src.app_services.beta import freeze_snapshot, verified_snapshot
from src.app_services.driver_explanations import build_driver_explanations, render_driver_explanations
from src.app_services.discord_reports import forecast_message
from src.app_services import forecast_automation
from src.model import build_model_features
from src.performance import add_performance_profile


def save_snapshot(folder, features, *, baseline=None, session='Q'):
    folder.mkdir(exist_ok=True)
    features.to_csv(folder / 'features.csv', index=False)
    pd.DataFrame({'Driver': features.Driver, 'avg_finish': [1.3, 1.7],
                  'win_chance': [.6, .4], 'dnf_chance': [.04, .05]}).to_csv(folder / 'simulation_summary.csv', index=False)
    if baseline is not None:
        baseline.to_csv(folder / 'baseline_race_features.csv', index=False)
    freeze_snapshot(folder, {'year': 2026, 'event': 'Test GP', 'session': session,
                            'race_start_utc': '2026-10-11T12:00:00Z'}, now='2026-10-10T16:00:00Z')
    return folder


@pytest.fixture
def inputs():
    current = pd.DataFrame({'Driver': ['A', 'B'], 'Team': ['T', 'T'], 'relative_pace': [.8, 0.],
                            'clean_laps': [6, 4], 'lap_std': [.2, .3], 'race_pace': [90.8, 90.],
                            'best_lap': [89.8, 89.], 'deg_per_lap': [.02, .03],
                            'raw_laps': [12, 10], 'dnf_prob': [.04, .05]})
    baseline = pd.DataFrame({'Driver': ['A', 'B', 'A', 'B'], 'Team': ['T'] * 4,
                            'relative_pace': [0., .6, .2, .8], 'baseline_age': [0, 0, 1, 1],
                            'source_round': [3, 3, 2, 2], 'source_year': [2026] * 4,
                            'source_event': ['Recent GP', 'Recent GP', 'Older GP', 'Older GP']})
    return current, baseline


def profile(current, baseline, session='Q'):
    result = add_performance_profile(build_model_features(current, baseline, session), current_session_type=session)
    result['grid_position'] = [7, 1]
    result['grid_source'] = ['actual_session_results', 'fia_official_grid']
    return result


def test_effective_share_reconstructs_both_blends_and_field_normalisation(tmp_path, inputs):
    current, baseline = inputs
    features = profile(current, baseline)
    folder = save_snapshot(tmp_path, features, baseline=baseline)
    explanation = build_driver_explanations(folder).set_index('Driver').loc['A']
    # Driver-specific second-stage weights make intermediate normalisation
    # material. Reconstruct it, rather than mislabelling weights as sensitivities.
    alpha, beta = features.effective_current_weight, features.race_weight_used
    history, weekend = features.baseline_relative_pace, features.current_relative_pace_capped
    first_blend = alpha * weekend + (1 - alpha) * history
    expected = (alpha * beta * weekend + (1 - alpha * beta) * history
                - beta * first_blend.min() - (1 - beta) * history.min())
    expected -= expected.min()
    assert features.race_pace_score.tolist() == pytest.approx(expected.tolist())
    assert explanation.current_pace_share == pytest.approx(.039375)
    assert '96.1%' in explanation.pace_explanation and '3.9%' in explanation.pace_explanation
    assert 'History ranks stronger' in explanation.pace_explanation
    assert 'Recent GP' in explanation.historical_races and 'Older GP' in explanation.historical_races
    assert '59.2%' in explanation.historical_races and '40.8%' in explanation.historical_races
    assert '6 usable laps' in explanation.evidence_limits
    assert 'not a measured sustained-run' in explanation.long_run_evidence


def test_unfrozen_history_is_never_used_and_original_files_are_unchanged(tmp_path, inputs):
    current, baseline = inputs
    save_snapshot(tmp_path, profile(current, baseline))
    source = tmp_path / 'source'
    source.mkdir()
    baseline.assign(source_event='UNVERIFIED GP').to_csv(source / 'baseline_race_features.csv', index=False)
    before = {p: p.read_bytes() for p in (tmp_path / 'frozen').iterdir()}
    paths = render_driver_explanations(tmp_path, tmp_path / 'preview')
    assert len(paths) == 3
    text = (tmp_path / 'preview/driver_explanations.md').read_text(encoding='utf-8')
    assert 'UNVERIFIED' not in text and 'identities unavailable' in text
    assert all(path.read_bytes() == content for path, content in before.items())


def test_pre_has_only_history_and_missing_baseline_withholds_share(tmp_path, inputs):
    current, baseline = inputs
    empty = current.iloc[:0]
    pre = profile(empty, baseline, 'PRE')
    folder = save_snapshot(tmp_path / 'pre', pre, session='PRE')
    result = build_driver_explanations(folder)
    assert result.current_pace_share.eq(0).all()
    assert result.evidence_limits.str.contains('no current-weekend').all()
    missing = profile(current, baseline.iloc[:0])
    folder = save_snapshot(tmp_path / 'missing', missing)
    assert build_driver_explanations(folder).current_pace_share.isna().all()


@pytest.mark.parametrize('kind', ['unknown', 'calibrated', 'duplicate', 'roster', 'nan_weight'])
def test_unsupported_or_invalid_inputs_do_not_invent_blend(tmp_path, inputs, kind):
    current, baseline = inputs
    features = profile(current, baseline)
    if kind == 'unknown':
        features['performance_model_version'] = 'future_model'
    elif kind == 'calibrated':
        features['historical_finish_weight'] = .3
    elif kind == 'duplicate':
        features.loc[1, 'Driver'] = features.loc[0, 'Driver']
    elif kind == 'nan_weight':
        features['effective_current_weight'] = float('nan')
    folder = save_snapshot(tmp_path, features)
    if kind == 'roster':
        # Re-freeze a new fixture with a feature roster different from the summary.
        features.loc[1, 'Driver'] = 'OUTSIDER'
        features.to_csv(folder / 'frozen/features.csv', index=False)
        from src.app_services.beta import digest
        path = folder / 'frozen/manifest.json'
        manifest = json.loads(path.read_text())
        manifest['files']['features.csv'] = digest(folder / 'frozen/features.csv')
        path.write_text(json.dumps(manifest))
    result = build_driver_explanations(folder)
    assert result.empty or result.current_pace_share.isna().all()


def test_matched_runs_are_identified_without_claiming_fuel_correction(tmp_path, inputs):
    current, baseline = inputs
    features = profile(current, baseline)
    features['performance_model_version'] = 'matched_stints_v2'
    features['matched_long_run_weight'] = .12
    features['long_run_laps'] = 12
    save_snapshot(tmp_path, features)
    result = build_driver_explanations(tmp_path)
    assert result.current_pace_share.eq(.12).all()
    assert result.pace_explanation.str.contains('12.0% matched practice').all()
    assert result.long_run_evidence.str.contains('12 laps').all()
    assert result.long_run_evidence.str.contains('Fuel load remains unknown').all()


def test_new_delivery_includes_all_driver_evidence_and_retry_keeps_plan(tmp_path, inputs, monkeypatch):
    current, baseline = inputs
    save_snapshot(tmp_path, profile(current, baseline), baseline=baseline)
    monkeypatch.setenv('DISCORD_REPORT_DETAIL', 'compact')
    plan = forecast_automation._forecast_delivery_plan(tmp_path)
    assert len(plan['files']) == 4
    assert plan['format_version'] == 3
    assert 'discord_report/driver_explanations.md' in [p.replace('\\', '/') for p in plan['files']]
    text = '\n'.join(f['value'] for f in plan['payload']['embeds'][0]['fields'])
    assert '96.1%' in text and 'not contributions to win probability' in text
    monkeypatch.setenv('DISCORD_REPORT_DETAIL', 'full')
    assert forecast_automation._forecast_delivery_plan(tmp_path) == plan
    # Baseline evidence is part of the same integrity contract as probabilities.
    (tmp_path / 'frozen/baseline_race_features.csv').write_text('tampered')
    with pytest.raises(ValueError, match='changed'):
        verified_snapshot(tmp_path)


def test_long_identifiers_fit_without_mentions(tmp_path, inputs):
    current, baseline = inputs
    features = profile(current, baseline)
    features['Driver'] = ['A' * 100 + '@everyone', 'B' * 100]
    folder = save_snapshot(tmp_path, features)
    message = forecast_message(folder)
    assert len(message['embeds'][0]['fields']) < 25
    assert '@everyone' not in json.dumps(message)


def test_empty_historical_file_and_missing_probability_are_explicit(tmp_path, inputs):
    current, baseline = inputs
    features = profile(current, baseline)
    folder = tmp_path
    features.to_csv(folder / 'features.csv', index=False)
    pd.DataFrame({'Driver': features.Driver, 'avg_finish': [1.3, 1.7]}).to_csv(folder / 'simulation_summary.csv', index=False)
    (folder / 'baseline_race_features.csv').write_text('\n')
    freeze_snapshot(folder, {'year': 2026, 'event': 'Test GP', 'session': 'Q',
                            'race_start_utc': '2026-10-11T12:00:00Z'}, now='2026-10-10T16:00:00Z')
    paths = render_driver_explanations(folder, folder / 'preview')
    assert len(paths) == 3
    text = (folder / 'preview/driver_explanations.md').read_text(encoding='utf-8')
    assert 'win unavailable' in text and 'identities unavailable' in text
    assert 'win 0.0%' not in text
