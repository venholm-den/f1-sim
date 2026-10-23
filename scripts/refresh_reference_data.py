"""Refresh reference CSVs from cached, attributable public source snapshots.

Downloads go to --output first. --apply validates and backs up the existing CSVs
before replacing them; no credentials or forecast files are accessed.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import sys
import time
from urllib.parse import urljoin

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_sources.fia_documents import parse_fia_document_listing_html, parse_fia_event_urls, merge_fia_document_rows
from src.track import DEFAULT_TRACK_PROFILE
from src.venues import CIRCUITS, legacy_circuit

FIA_URL = 'https://www.fia.com/documents/championships/fia-formula-one-world-championship-14/season/season-2026-2072'
CURRENT_PU_SOURCE = 'https://www.formula1.com/en/latest/article/all-you-need-to-know-about-f1s-new-power-units.14jfv7a36905uDJDdNyfQd'
PREVIOUS_PU_SOURCE = 'https://www.fia.com/sites/default/files/media_kit_-_2025_singapore_grand_prix_0.pdf'
BADGE_SOURCES = {
    'TAG Heuer': 'https://www.formula1.com/en/latest/article/red-bull-and-tag-heuer-extend-engine-naming-partnership.37dnjbA2VWSMgUlN7E1bYL',
}
ENGINE_BADGES = (
    'Honda RBPT', 'TAG Heuer', 'Mugen Honda', 'Mugen-Honda', 'Motori Moderni',
    'Alfa Romeo', 'Ford Cosworth', 'TAG Porsche', 'Mercedes', 'Ferrari', 'Renault',
    'Honda', 'RBPT', 'BMW', 'Toyota', 'Cosworth', 'Ford', 'Climax', 'BRM', 'Repco',
    'Maserati', 'Vanwall', 'Porsche', 'TAG', 'Peugeot', 'Supertec', 'Mecachrome',
    'Playlife', 'Petronas', 'Asiatech', 'Judd', 'Hart', 'Yamaha', 'Lamborghini',
    'Zakspeed', 'Acer', 'Serenissima', 'Borgward', 'ATS', 'Aston Martin',
    'Offenhauser', 'Talbot-Lago', 'Simca-Gordini', 'Gordini', 'Speluzzi',
    'Lea Francis', 'Bristol', 'Lancia', 'Mercedes-Benz', 'Alta', 'Novi',
    'Castellotti', 'Weslake', 'Matra', 'Tecno', 'Megatron', 'Ilmor',
)
GEOMETRY_PAGES = {
    'albert_park': (2026, 'australia'), 'shanghai': (2026, 'china'), 'suzuka': (2026, 'japan'),
    'miami': (2026, 'miami'), 'villeneuve': (2026, 'canada'), 'monaco': (2026, 'monaco'),
    'catalunya': (2026, 'barcelona-catalunya'), 'red_bull_ring': (2026, 'austria'),
    'silverstone': (2026, 'great-britain'), 'spa': (2026, 'belgium'), 'hungaroring': (2026, 'hungary'),
    'zandvoort': (2026, 'netherlands'), 'monza': (2026, 'italy'), 'madring': (2026, 'spain'),
    'baku': (2026, 'azerbaijan'), 'sepang': (2026, 'bahrain'), 'marina_bay': (2026, 'singapore'),
    'americas': (2026, 'united-states'), 'rodriguez': (2026, 'mexico'), 'interlagos': (2026, 'brazil'),
    'vegas': (2026, 'las-vegas'), 'losail': (2026, 'qatar'), 'yas_marina': (2026, 'united-arab-emirates'),
    'bahrain': (2025, 'bahrain'), 'jeddah': (2025, 'saudi-arabia'), 'imola': (2025, 'emiliaromagna'),
}
VERIFIED_ENGINE_OVERRIDES = {
    (2017, 'Toro Rosso'): ('Renault', 'https://www.formula1.com/en/latest/article/red-bull-racing-and-toro-rosso-to-use-renault-power-in-2017-.74PU7IMAtxtx48mNbMTGFL'),
    (2018, 'Force India Sahara'): ('Mercedes', 'https://www.fia.com/sites/default/files/2018_fia_f1_abu_dhabi_gp_-_media_kit.pdf'),
}
TEAM_ALIASES = {
    'STR': ['Toro Rosso', 'Scuderia Toro Rosso'], 'Toro Rosso': ['Scuderia Toro Rosso'],
    'AlphaTauri': ['Alpha Tauri', 'Scuderia AlphaTauri'], 'Haas': ['Haas F1 Team'],
    'Haas F1 Team': ['Haas'], 'Lotus': ['Lotus F1', 'Lotus F1 Team'],
    'Force India': ['Sahara Force India'], 'Racing Point': ['Racing Point Force India'],
    'Alfa Romeo': ['Alfa Romeo Racing'], 'Kick Sauber': ['Sauber', 'Stake F1 Team Kick Sauber'],
    'Aston Martin Aramco': ['Aston Martin', 'Aston Martin Aramco Mercedes'],
    'Aston Martin': ['Aston Martin Aramco'], 'RB': ['RB F1 Team', 'Visa Cash App RB'],
}


class TableParser(HTMLParser):
    """Read text cells without installing an HTML parsing dependency."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.rows, self.row, self.cell = [], None, None, None

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.rows = []
        elif tag == 'tr' and self.rows is not None:
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == 'table' and self.rows is not None:
            self.tables.append(self.rows)
            self.rows = None


def fetch(url, output):
    cache = output / 'sources' / (hashlib.sha256(url.encode()).hexdigest() + '.txt')
    if cache.exists():
        return cache.read_text(encoding='utf-8')
    response = requests.get(url, timeout=45)
    response.raise_for_status()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(response.text, encoding='utf-8')
    cache.with_suffix('.json').write_text(json.dumps({'url': url, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
        'sha256': hashlib.sha256(response.content).hexdigest(), 'status': response.status_code}, indent=2))
    time.sleep(.35)
    return response.text


def season_urls(html):
    return {int(year): urljoin('https://www.fia.com', path) for path, year in re.findall(
        r'<option[^>]+value="([^"]*/championships/fia-formula-one-world-championship-14/season/season-(\d{4})-\d+)"', html)}


def team_labels(html):
    parser = TableParser()
    parser.feed(html)
    for table in parser.tables:
        if table and table[0] == ['Pos.', 'Team', 'Pts.']:
            return [row[1] for row in table[1:] if len(row) == 3]
        if table and table[0] == ['Pos.', 'Driver', 'Nationality', 'Team', 'Pts.']:
            return sorted({row[3] for row in table[1:] if len(row) == 5 and row[3]})
    raise ValueError('Official team standings table is absent; snapshot not accepted.')


def split_engine(label):
    for badge in sorted(ENGINE_BADGES, key=len, reverse=True):
        if label == badge:
            return label, badge
        if label.endswith(' ' + badge):
            return label[:-len(badge)-1], badge
    return None


def circuit_geometry(html):
    values = dict(re.findall(r'<dt\b[^>]*>([^<]+)</dt>\s*<dd\b[^>]*>([^<]+)</dd>', html))
    fields = {'Circuit Length': 'CircuitLengthKm', 'Number of Laps': 'RaceLaps',
              'Race Distance': 'RaceDistanceKm', 'First Grand Prix': 'FirstGrandPrix'}
    if 'Circuit Length' not in values:
        raise ValueError('Official circuit statistics are absent; geometry withheld.')
    return {field: float(values[key].replace('km', '')) for key, field in fields.items() if key in values}


def collect(output):
    failures = []
    main = fetch(FIA_URL, output)
    seasons = season_urls(main)
    seasons[2026] = FIA_URL  # Current selected option uses value=0 in FIA HTML.
    listings = []
    event_counts = {}
    for year, url in sorted(seasons.items()):
        html = fetch(url, output)
        year_listings = parse_fia_document_listing_html(html, year, url)
        links = parse_fia_event_urls(html, url)
        with ThreadPoolExecutor(max_workers=3) as pool:
            jobs = {pool.submit(fetch, event_url, output): event_url for event_url in links}
            for job in as_completed(jobs):
                try:
                    event_url = jobs[job]
                    year_listings.extend(parse_fia_document_listing_html(job.result(), year, event_url))
                except Exception as exc:
                    failures.append({'source': jobs[job], 'error': str(exc)})
        listings.extend(row.to_row() for row in year_listings)
        event_counts[year] = {'event_pages': len(links), 'listing_rows': len(year_listings)}
        print(f'FIA {year}: {len(links)} event pages, {len(year_listings)} listing rows', flush=True)
    (output / 'fia-listings.json').write_text(json.dumps(listings, ensure_ascii=False))
    teams = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(fetch, f'https://www.formula1.com/en/results/{year}/{"team" if year >= 1958 else "drivers"}', output): year for year in range(1950, 2027)}
        for job in as_completed(jobs):
            year = jobs[job]
            try:
                teams[year] = team_labels(job.result())
            except Exception as exc:
                failures.append({'source': f'F1 team standings {year}', 'error': str(exc)})
    (output / 'teams.json').write_text(json.dumps(teams, ensure_ascii=False))
    circuits = json.loads(fetch('https://api.jolpi.ca/ergast/f1/circuits.json?limit=100', output))['MRData']
    if int(circuits['total']) > len(circuits['CircuitTable']['Circuits']):
        raise ValueError('Circuit endpoint is paginated; do not accept an incomplete catalogue.')
    (output / 'circuits.json').write_text(json.dumps(circuits['CircuitTable']['Circuits']))
    races, offset = [], 0
    while True:
        data = json.loads(fetch(f'https://api.jolpi.ca/ergast/f1/races.json?limit=100&offset={offset}', output))['MRData']
        batch = data['RaceTable']['Races']
        if not batch:
            break
        races.extend(batch)
        offset += len(batch)
        if offset >= int(data['total']):
            break
    (output / 'races.json').write_text(json.dumps(races))
    geometry = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(fetch, f'https://www.formula1.com/en/racing/{year}/{slug}', output): (identifier, year, slug)
                for identifier, (year, slug) in GEOMETRY_PAGES.items()}
        for job in as_completed(jobs):
            identifier, year, slug = jobs[job]
            try:
                geometry[identifier] = {**circuit_geometry(job.result()), 'GeometrySeason': year,
                    'GeometrySourceURL': f'https://www.formula1.com/en/racing/{year}/{slug}'}
            except Exception as exc:
                failures.append({'source': f'Circuit geometry {identifier}', 'error': str(exc)})
    (output / 'geometry.json').write_text(json.dumps(geometry, indent=2))
    report = {'fia_seasons': event_counts, 'team_seasons': sorted(teams), 'circuits': len(circuits['CircuitTable']['Circuits']),
              'calendar_races': len(races), 'published_geometry_circuits': len(geometry), 'failures': failures}
    (output / 'collection.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


def build(output):
    original = pd.read_csv(ROOT / 'data/track_profiles.csv').fillna('')
    rows = original.to_dict('records')
    circuits = json.loads((output / 'circuits.json').read_text())
    races = json.loads((output / 'races.json').read_text())
    calendar = {}
    for race in races:
        calendar.setdefault(race['Circuit']['circuitId'], []).append(race)
    catalogue = {c['circuitId']: c for c in circuits}
    geometry = json.loads((output / 'geometry.json').read_text()) if (output / 'geometry.json').exists() else {}
    for row in rows:
        row['CircuitId'] = row.get('CircuitId') or legacy_circuit(row['Event'])
    for identifier, circuit in catalogue.items():
        if not any(row['CircuitId'] == identifier for row in rows):
            events = calendar.get(identifier, [])
            event = max(events, key=lambda x: (int(x['season']), int(x['round'])))['raceName'] if events else circuit['circuitName']
            rows.append({'Event': event, 'CircuitId': identifier,
                'OvertakingDifficulty': DEFAULT_TRACK_PROFILE['overtaking_difficulty'],
                'SafetyCarChance': DEFAULT_TRACK_PROFILE['safety_car_chance'],
                'RedFlagBaseChance': DEFAULT_TRACK_PROFILE['red_flag_base_chance'],
                'ProfileStatus': 'generic_uncalibrated', 'Notes': 'Reference circuit metadata; risk/overtaking factors are generic defaults, not measured circuit rates.'})
    for row in rows:
        c = catalogue.get(row['CircuitId'])
        if c:
            row.update(CircuitName=c['circuitName'], Country=c['Location']['country'], Locality=c['Location']['locality'],
                Latitude=c['Location']['lat'], Longitude=c['Location']['long'],
                SourceURL='https://api.jolpi.ca/ergast/f1/circuits.json?limit=100', ReferenceURL=c['url'])
        elif row['CircuitId'] in CIRCUITS:
            c = CIRCUITS[row['CircuitId']]
            row.update(CircuitName=c['circuit_name'], Latitude=c['latitude'], Longitude=c['longitude'], Country=c['venue_country'])
        history = calendar.get(row['CircuitId'], [])
        row['FirstSeason'] = min((int(r['season']) for r in history), default='')
        row['LastSeason'] = max((int(r['season']) for r in history), default='')
        row['EventAliases'] = ' | '.join(sorted({r['raceName'] for r in history}))
        row.setdefault('ProfileStatus', 'existing_circuit_heuristic')
        row['VerifiedAtUTC'] = datetime.now(timezone.utc).date().isoformat()
        row.update(geometry.get(row['CircuitId'], {}))
    # Keep every existing event row and order; exact circuit identity handles reused race names.
    pd.DataFrame(rows).to_csv(output / 'track_profiles.csv', index=False)
    mapping = pd.read_csv(ROOT / 'data/team_power_units.csv').fillna('').to_dict('records')
    for row in mapping:
        if int(row['Year']) in (2025, 2026):
            row['SourceURL'] = PREVIOUS_PU_SOURCE if int(row['Year']) == 2025 else CURRENT_PU_SOURCE
            row['VerifiedAtUTC'] = datetime.now(timezone.utc).date().isoformat()
            row['EngineBadge'] = row['PowerUnitSupplier']
    keys = {(int(r['Year']), r['Team'].casefold()) for r in mapping}
    for row in list(mapping):
        for alias in TEAM_ALIASES.get(row['Team'], []):
            key = (int(row['Year']), alias.casefold())
            if key not in keys:
                mapping.append({**row, 'Team': alias, 'AliasFor': row['Team'],
                    'Notes': f"Lookup alias for {row['Team']}; does not assert a separate entrant. " + row['Notes']})
                keys.add(key)
    unresolved, candidates = [], {}
    teams = json.loads((output / 'teams.json').read_text())
    for year_text, labels in sorted(teams.items()):
        year = int(year_text)
        for label in labels:
            override = VERIFIED_ENGINE_OVERRIDES.get((year, label))
            # Since 2025 the standings omit engines from customer team labels.
            # A bare 'Aston Martin' must not imply an Aston Martin-built engine.
            parsed = None if year >= 2025 else (label, override[0]) if override else split_engine(label)
            if not parsed:
                if year < 2025:
                    unresolved.append({'year': year, 'label': label})
                continue
            team, badge = parsed
            supplier = 'Renault' if badge == 'TAG Heuer' else badge
            aliases = [label, team]
            if year >= 2010:
                aliases.extend(TEAM_ALIASES.get(team, []))
            for alias in aliases:
                candidates.setdefault((year, alias), []).append((supplier, badge, label, override[1] if override else ''))
    ambiguous = []
    for (year, alias), values in sorted(candidates.items()):
        if (year, alias.casefold()) in keys:
            continue
        if len({value[0] for value in values}) != 1:
            ambiguous.append({'year': year, 'team': alias, 'badges': sorted({v[1] for v in values})})
            continue
        supplier, badge, label, override_url = values[0]
        mapping.append({'Year': year, 'Team': alias, 'PowerUnitSupplier': supplier, 'EngineBadge': badge,
            'OfficialTeamLabel': label, 'SourceURL': override_url or f'https://www.formula1.com/en/results/{year}/{"team" if year >= 1958 else "drivers"}',
            'BadgeSourceURL': BADGE_SOURCES.get(badge, ''), 'VerifiedAtUTC': datetime.now(timezone.utc).date().isoformat(),
            'Notes': 'Historical engine supplier/badge from official F1 standings; before 2014 this is an engine, not a hybrid power unit.'})
        keys.add((year, alias.casefold()))
    pd.DataFrame(mapping).sort_values(['Year', 'Team']).to_csv(output / 'team_power_units.csv', index=False)
    existing = pd.read_csv(ROOT / 'data/fia_documents/fia_document_index.csv')
    # Reparse cached snapshots as well, so a parser repair needs no redownload.
    listings, quarantined = [], []
    for provenance in (output / 'sources').glob('*.json'):
        url = json.loads(provenance.read_text())['url']
        year_match = re.search(r'fia-formula-one-world-championship-14/season/season-(\d{4})-', url)
        if year_match:
            for row in parse_fia_document_listing_html(
                provenance.with_suffix('.txt').read_text(encoding='utf-8'), int(year_match.group(1)), url):
                published_year = re.search(r'\b\d{2}\.\d{2}\.(\d{2})\b', row.published_at)
                file_years = re.findall(r'(?<!\d)(20\d{2})(?!\d)', row.document_url.rsplit('/', 1)[-1])
                if published_year and file_years and int('20' + published_year.group(1)) != row.year and str(row.year) not in file_years:
                    quarantined.append(row.to_row())
                else:
                    listings.append(row.to_row())
    updated = merge_fia_document_rows(existing, listings)
    updated.to_csv(output / 'fia_document_index.csv', index=False)
    report = {'tracks_before': len(original), 'tracks_after': len(rows), 'circuits': len({r['CircuitId'] for r in rows}),
        'power_units_after': len(mapping), 'power_unit_unresolved': unresolved, 'ambiguous_team_aliases_omitted': ambiguous,
        'fia_before': len(existing), 'fia_after': len(updated), 'fia_years': updated.groupby('year').size().to_dict(),
        'fia_misdated_listings_quarantined': quarantined}
    (output / 'build-summary.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


def validate(output):
    tracks = pd.read_csv(output / 'track_profiles.csv')
    units = pd.read_csv(output / 'team_power_units.csv')
    fia = pd.read_csv(output / 'fia_document_index.csv')
    assert tracks['CircuitId'].notna().all(), 'Track identity is missing.'
    assert not tracks.duplicated(['Event', 'CircuitId']).any(), 'Duplicate track identity.'
    assert pd.to_numeric(tracks.Latitude).between(-90, 90).all(), 'Invalid latitude.'
    assert pd.to_numeric(tracks.Longitude).between(-180, 180).all(), 'Invalid longitude.'
    for name in ['OvertakingDifficulty', 'SafetyCarChance', 'RedFlagBaseChance']:
        assert pd.to_numeric(tracks[name]).between(0, 1).all(), f'Invalid probability: {name}'
    assert not units.assign(team_key=units.Team.str.casefold()).duplicated(['Year', 'team_key']).any(), 'Conflicting supplier rows.'
    assert units[['Year', 'Team', 'PowerUnitSupplier', 'SourceURL']].notna().all().all(), 'Incomplete supplier provenance.'
    assert fia[['year', 'event', 'document_title', 'document_url']].notna().all().all(), 'Incomplete FIA metadata.'
    assert fia.document_url.str.startswith('https://www.fia.com/').all(), 'Non-FIA document URL.'
    for target, frame in [('data/track_profiles.csv', tracks), ('data/team_power_units.csv', units), ('data/fia_documents/fia_document_index.csv', fia)]:
        assert len(frame) >= len(pd.read_csv(ROOT / target)), f'Coverage regression: {target}'
    return {'track_rows': len(tracks), 'circuits': tracks.CircuitId.nunique(), 'supplier_rows': len(units),
            'supplier_years': [int(units.Year.min()), int(units.Year.max())], 'fia_rows': len(fia),
            'fia_seasons': sorted(fia.year.unique().tolist()), 'fia_event_seasons': len(fia[['year', 'event']].drop_duplicates()),
            'geometry_circuits': tracks.dropna(subset=['CircuitLengthKm']).CircuitId.nunique()}


def apply(output):
    validation = validate(output)
    targets = ['data/track_profiles.csv', 'data/team_power_units.csv', 'data/fia_documents/fia_document_index.csv']
    backups = output / 'before'
    backups.mkdir(exist_ok=True)
    for target in targets:
        source, current = output / Path(target).name, ROOT / target
        if not (backups / Path(target).name).exists():
            shutil.copy2(current, backups / Path(target).name)
        replacement = current.with_suffix('.csv.tmp')
        shutil.copy2(source, replacement)
        replacement.replace(current)
    print('Applied three reference CSVs. Original copies retained in ' + str(backups))
    (output / 'validation.json').write_text(json.dumps(validation, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.collect:
        collect(args.output)
    if args.build:
        build(args.output)
    if args.apply:
        apply(args.output)
