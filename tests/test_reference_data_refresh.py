import pandas as pd
import pytest

from scripts.refresh_reference_data import circuit_geometry, season_urls, split_engine, team_labels
from src.data_sources.fia_documents import parse_fia_document_listing_html, fia_f1_documents_url, infer_fia_session
from src.reliability import _power_unit_for_team
from src.track import load_track_profile


def test_older_fia_titles_keep_real_metadata_without_inventing_document_numbers():
    html = '''<div class="event-title">Singapore Grand Prix</div>
    <li class="document-row"><a href="/sites/default/files/2019_final_race_classification.pdf">
    <div class="title"><div class="field"><div>Final Race Classification</div></div></div>
    <div class="published"><div>Published on <span>22.09.19 19:11</span> CET</div></div>
    </a></li>'''
    row, = parse_fia_document_listing_html(html, 2019)
    assert row.doc_number == ''
    assert row.event == 'Singapore Grand Prix' and row.session == 'R'
    assert row.document_type == 'race classification'
    assert row.published_at == '22.09.19 19:11 CET'
    assert row.to_row()['status'] == 'metadata'
    assert row.to_row()['classification_position'] == ''


def test_numbered_fia_titles_and_season_configuration_remain_supported():
    html = '''<div class="event-title">British Grand Prix</div><li class="document-row">
    <a href="/grid.pdf"><div class="title">Doc. 20 - Final Starting Grid</div></a></li>'''
    row, = parse_fia_document_listing_html(html, 2025)
    assert row.doc_number == 'Doc 20' and row.document_type == 'final starting grid'
    assert 'season-2025-2071' in fia_f1_documents_url(2025)
    assert infer_fia_session('Sprint Qualifying Classification', year=2021) == 'S'
    assert infer_fia_session('Sprint Shootout Classification', year=2023) == 'SQ'
    assert infer_fia_session('Sprint Qualifying Classification', year=2025) == 'SQ'


def test_engine_lookup_requires_the_requested_season():
    mapping = pd.DataFrame({'Year': [2014, 2015, 2018], 'Team': ['McLaren'] * 3,
                            'team_key': ['mclaren'] * 3, 'PowerUnitSupplier': ['Mercedes', 'Honda', 'Renault']})
    assert _power_unit_for_team('McLaren', 2014, mapping) == 'Mercedes'
    assert _power_unit_for_team('McLaren', 2015, mapping) == 'Honda'
    assert _power_unit_for_team('McLaren', 2018, mapping) == 'Renault'
    assert _power_unit_for_team('McLaren', 2013, mapping) == 'Unknown'
    assert _power_unit_for_team('McLaren', 2016, mapping) == 'Unknown'
    assert _power_unit_for_team('McLaren', 2026, mapping) == 'Unknown'


def test_reference_only_track_is_not_reported_as_a_calibrated_profile(tmp_path):
    path = tmp_path / 'tracks.csv'
    pd.DataFrame([{'Event': 'Malaysian Grand Prix', 'CircuitId': 'sepang',
        'OvertakingDifficulty': .55, 'SafetyCarChance': .4, 'RedFlagBaseChance': .035,
        'ProfileStatus': 'generic_uncalibrated'}]).to_csv(path, index=False)
    profile = load_track_profile('Bahrain Grand Prix', str(path), metadata={'year': 2026, 'event': 'Bahrain Grand Prix'})
    assert profile['circuit_id'] == 'sepang'
    assert profile['profile_status'] == 'generic_uncalibrated'
    assert 'calibration unavailable' in profile['notes']


def test_source_parsers_keep_badges_and_geometry_season_distinct():
    assert split_engine('Red Bull Racing Honda RBPT') == ('Red Bull Racing', 'Honda RBPT')
    assert split_engine('Red Bull Racing TAG Heuer') == ('Red Bull Racing', 'TAG Heuer')
    assert split_engine('Unpublished Engine') is None
    html = '<table><tr><th>Pos.</th><th>Team</th><th>Pts.</th></tr><tr><td>1</td><td>McLaren Mercedes</td><td>100</td></tr></table>'
    assert team_labels(html) == ['McLaren Mercedes']
    assert season_urls('<option value="/documents/championships/fia-formula-one-world-championship-14/season/season-2024-2043">2024</option>')[2024].endswith('season-2024-2043')
    assert circuit_geometry('<dl><dt>Circuit Length</dt><dd>5.543km</dd><dt>Number of Laps</dt><dd>56</dd></dl>') == {'CircuitLengthKm': 5.543, 'RaceLaps': 56.0}
    with pytest.raises(ValueError, match='absent'):
        circuit_geometry('<html>Missing circuit statistics</html>')
