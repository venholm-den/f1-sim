"""Compare nine excluded Q fields with F1's complete published result tables.

Retains raw HTML and special positions. Never substitutes table order, starting
grid or lap-time rank for an official numeric qualifying position.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path

import pandas as pd
import requests

from src.circuit_calibration import sha256

# Explicit result identities, independently located on formula1.com.
CASES = (
    (2021, 5, 1067, 'monaco', 'MONACO'),
    (2023, 10, 1214, 'great-britain', 'BRITISH'),
    (2024, 8, 1236, 'monaco', 'MONACO'),
    (2024, 15, 1243, 'netherlands', 'DUTCH'),
    (2024, 17, 1245, 'azerbaijan', 'AZERBAIJAN'),
    (2025, 7, 1260, 'emilia-romagna', 'EMILIA'),
    (2025, 21, 1273, 'brazil', 'PAULO'),
    (2026, 1, 1279, 'australia', 'AUSTRALIAN'),
    (2026, 14, 1294, 'spain', 'ESPAÑA'),
)


class ResultTable(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.row, self.cell, self.title = [], None, None, ''
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == 'h1':
            self.in_title = True
        elif tag == 'tr':
            self.row = []
        elif tag == 'td' and self.row is not None:
            self.cell = ''

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if tag == 'h1':
            self.in_title = False
        elif tag == 'td' and self.cell is not None:
            self.row.append(' '.join(self.cell.split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None


def parse_classification(html, year, token):
    table = ResultTable()
    table.feed(html)
    title = table.title.upper()
    if str(year) not in title or token not in title or 'QUALIFYING' not in title:
        raise ValueError('Official page identity/session mismatch.')
    if not table.rows or any(len(row) != 8 for row in table.rows):
        raise ValueError('Expected one complete eight-column qualifying table.')
    frame = pd.DataFrame(table.rows, columns=['OfficialPosition', 'DriverNumber',
        'OfficialDriver', 'OfficialTeam', 'Q1', 'Q2', 'Q3', 'Laps'])
    if not frame.DriverNumber.str.fullmatch(r'\d+').all() or frame.DriverNumber.duplicated().any():
        raise ValueError('Invalid/duplicate official driver numbers.')
    return frame, table.title


def complete_numeric_positions(frame):
    ranks = pd.to_numeric(frame.OfficialPosition, errors='coerce')
    return bool(len(frame) >= 2 and ranks.notna().all()
                and sorted(ranks) == list(range(1, len(frame)+1)))


def run(workspace, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    library = Path(workspace)/'data/historical_library'
    manifests = {}
    for path in library.glob('*/detailed/*/session.json'):
        m = json.loads(path.read_text(encoding='utf-8'))
        if m.get('session') == 'Q' and m.get('status') == 'complete':
            key = m['year'], m['round']
            if key in manifests:
                raise ValueError('Ambiguous archive Q partition.')
            manifests[key] = path, m
    reports, comparisons, corrections = [], [], []
    for year, round_number, result_id, slug, token in CASES:
        url = f'https://www.formula1.com/en/results/{year}/races/{result_id}/{slug}/qualifying'
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
        page = output/f'{year}_{round_number}_official.html'
        page.write_bytes(response.content)
        official, title = parse_classification(response.text, year, token)
        path, m = manifests[year, round_number]
        files = [(path.parent/name, info) for name, info in m['files'].items() if info['table'] == 'results']
        if len(files) != 1 or sha256(files[0][0]) != files[0][1]['sha256']:
            raise ValueError('Archive classification checksum mismatch.')
        archived = pd.read_csv(files[0][0], dtype={'DriverNumber': str})
        archived['DriverNumber'] = pd.to_numeric(archived.DriverNumber, errors='raise').astype(int).astype(str)
        if archived.DriverNumber.duplicated().any():
            raise ValueError('Duplicate saved driver numbers.')
        same_roster = set(archived.DriverNumber) == set(official.DriverNumber)
        missing = sorted(set(archived.DriverNumber) - set(official.DriverNumber))
        extra = sorted(set(official.DriverNumber) - set(archived.DriverNumber))
        joined = archived[['DriverNumber', 'Abbreviation', 'Position']].merge(
            official, on='DriverNumber', how='outer', validate='one_to_one')
        joined.insert(0, 'Round', round_number)
        joined.insert(0, 'Year', year)
        joined['SourceURL'] = url
        official_rank = pd.to_numeric(joined.OfficialPosition, errors='coerce')
        old_rank = pd.to_numeric(joined.Position, errors='coerce')
        changed = ~(old_rank.eq(official_rank) | (old_rank.isna() & official_rank.isna()))
        numeric_complete = same_roster and complete_numeric_positions(official)
        joined.to_csv(output/f'{year}_{round_number}_comparison.csv', index=False)
        comparisons.append(joined)
        if numeric_complete:
            correction = joined.copy()
            correction['Position'] = official_rank
            correction['Event'] = m['event']
            correction['Session'] = 'Q'
            corrections.append(correction)
        reports.append({'year': year, 'round': round_number, 'event': m['event'],
            'source_url': url, 'resolved_url': response.url, 'title': title,
            'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
            'html_sha256': sha256(page), 'archive_manifest_sha256': sha256(path),
            'archive_results_sha256': sha256(files[0][0]), 'complete_roster_verified': same_roster,
            'missing_official_driver_numbers': missing, 'extra_official_driver_numbers': extra,
            'drivers': len(joined), 'complete_numeric_classification': numeric_complete,
            'special_positions': joined.loc[official_rank.isna(), ['Abbreviation', 'OfficialPosition']].to_dict('records'),
            'numeric_disagreements': joined.loc[changed, ['Abbreviation', 'Position', 'OfficialPosition']].to_dict('records'),
            'action': 'explicit_offline_overlay_available' if numeric_complete else 'retain_exclusion_full_field_contract',
            'archive_mutated': False})
    pd.concat(comparisons, ignore_index=True).to_csv(output/'comparisons.csv', index=False)
    if corrections:
        pd.concat(corrections, ignore_index=True).to_csv(output/'verified_complete_classifications.csv', index=False)
    report = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'cases': reports,
        'complete_rosters_verified': sum(r['complete_roster_verified'] for r in reports),
        'recoverable_complete_fields': len(corrections),
        'archive_mutated': False, 'activated': False,
        'interpretation': 'Complete entrant tables can legitimately contain DQ/NC and no full-field numeric permutation. '
            'No rank is inferred from row order, lap times or Sunday grid. Independent source means F1 website '
            'rather than the saved FastF1 table; underlying timing origins may be shared.',
        'source_sha256': sha256(Path(__file__))}
    # Nulls, not nonstandard JSON NaN, for absent archive ranks.
    report = json.loads(pd.Series([report]).to_json(orient='values'))[0]
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.workspace, args.output_dir), indent=2))


if __name__ == '__main__':
    main()
