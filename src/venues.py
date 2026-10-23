"""Circuit identity is independent of the commercial Grand Prix name.

Current calendar coordinates: Jolpica 2026 schedule, checked 2026-10-05 via FastF1 Ergast.
Jeddah and Imola retain legacy reference coordinates outside the current calendar.
https://api.jolpi.ca/ergast/f1/2026.json
2026 Sepang: https://www.formula1.com/en/latest/article/formula-1-gulf-air-bahrain-grand-prix-in-malaysia-2026.1IHoy7D2dfCIugb5mH78cE
2026 Madring: https://www.astonmartinf1.com/en-GB/races/2026-spanish-gp/
Other lap counts remain conventional circuit assumptions, not race bulletins.
"""
from __future__ import annotations

import unicodedata


def _clean(value) -> str:
    text = unicodedata.normalize('NFKD', str(value or ''))
    return ' '.join(''.join(c.lower() if c.isalnum() else ' ' for c in text if not unicodedata.combining(c)).split())


# ID, display name, country, coordinates, conventional laps, location aliases.
_ROWS = [
    ('bahrain', 'Bahrain International Circuit', 'Bahrain', 26.0325, 50.5106, 57, ('Sakhir', 'Manama', 'Bahrain')),
    ('sepang', 'Sepang International Circuit', 'Malaysia', 2.76083, 101.738, 56, ('Sepang', 'Kuala Lumpur')),
    ('madring', 'Madring', 'Spain', 40.46528, -3.61528, 57, ('Madrid', 'Madring')),
    ('albert_park', 'Albert Park Grand Prix Circuit', 'Australia', -37.8497, 144.968, 58, ('Melbourne', 'Albert Park')),
    ('shanghai', 'Shanghai International Circuit', 'China', 31.3389, 121.22, 56, ('Shanghai',)),
    ('suzuka', 'Suzuka Circuit', 'Japan', 34.8431, 136.541, 53, ('Suzuka',)),
    ('miami', 'Miami International Autodrome', 'USA', 25.9581, -80.2389, 57, ('Miami', 'Miami Gardens')),
    ('villeneuve', 'Circuit Gilles Villeneuve', 'Canada', 45.5, -73.5228, 70, ('Montreal', 'Montréal')),
    ('monaco', 'Circuit de Monaco', 'Monaco', 43.7347, 7.42056, 78, ('Monte Carlo', 'Monaco')),
    ('catalunya', 'Circuit de Barcelona-Catalunya', 'Spain', 41.57, 2.26111, 66, ('Barcelona', 'Catalunya', 'Montmelo')),
    ('red_bull_ring', 'Red Bull Ring', 'Austria', 47.2197, 14.7647, 71, ('Spielberg',)),
    ('silverstone', 'Silverstone Circuit', 'UK', 52.0786, -1.01694, 52, ('Silverstone',)),
    ('spa', 'Circuit de Spa-Francorchamps', 'Belgium', 50.4372, 5.97139, 44, ('Spa', 'Spa-Francorchamps')),
    ('hungaroring', 'Hungaroring', 'Hungary', 47.5789, 19.2486, 70, ('Budapest', 'Hungaroring')),
    ('zandvoort', 'Circuit Zandvoort', 'Netherlands', 52.3888, 4.54092, 72, ('Zandvoort',)),
    ('monza', 'Autodromo Nazionale Monza', 'Italy', 45.6156, 9.28111, 53, ('Monza',)),
    ('baku', 'Baku City Circuit', 'Azerbaijan', 40.3725, 49.8533, 51, ('Baku',)),
    ('marina_bay', 'Marina Bay Street Circuit', 'Singapore', 1.2914, 103.864, 62, ('Singapore', 'Marina Bay')),
    ('americas', 'Circuit of the Americas', 'USA', 30.1328, -97.6411, 56, ('Austin',)),
    ('rodriguez', 'Autodromo Hermanos Rodriguez', 'Mexico', 19.4042, -99.0907, 71, ('Mexico City',)),
    ('interlagos', 'Autodromo Jose Carlos Pace', 'Brazil', -23.7036, -46.6997, 71, ('Sao Paulo', 'Interlagos')),
    ('vegas', 'Las Vegas Strip Circuit', 'USA', 36.1147, -115.173, 50, ('Las Vegas',)),
    ('losail', 'Lusail International Circuit', 'Qatar', 25.49, 51.4542, 57, ('Lusail', 'Losail')),
    ('yas_marina', 'Yas Marina Circuit', 'UAE', 24.4672, 54.6031, 58, ('Abu Dhabi', 'Yas Marina', 'Yas Island')),
    ('jeddah', 'Jeddah Corniche Circuit', 'Saudi Arabia', 21.6319, 39.1044, 50, ('Jeddah',)),
    ('imola', 'Autodromo Enzo e Dino Ferrari', 'Italy', 44.3439, 11.7167, 63, ('Imola',)),
    # Historical archive locations; coordinates match data/track_profiles.csv.
    ('ricard', 'Circuit Paul Ricard', 'France', 43.2506, 5.79167, 53, ('Le Castellet', 'Paul Ricard')),
    ('portimao', 'Autódromo Internacional do Algarve', 'Portugal', 37.2270, -8.6267, 66, ('Portimão', 'Portimao', 'Algarve')),
    ('sochi', 'Sochi Autodrom', 'Russia', 43.4057, 39.9578, 53, ('Sochi',)),
    ('istanbul', 'Istanbul Park', 'Turkey', 40.9517, 29.405, 58, ('Istanbul',)),
]
CIRCUITS = {row[0]: {'circuit_id': row[0], 'circuit_name': row[1], 'venue_country': row[2],
                     'latitude': row[3], 'longitude': row[4], 'race_laps': row[5], 'aliases': row[6]} for row in _ROWS}
LEGACY_EVENTS = dict(zip([
    'Bahrain', 'Saudi Arabian', 'Australian', 'Chinese', 'Japanese', 'Miami', 'Canadian', 'Monaco',
    'Barcelona', 'Spanish', 'Austrian', 'British', 'Belgian', 'Hungarian', 'Dutch', 'Italian',
    'Azerbaijan', 'Singapore', 'United States', 'Mexico City', 'Brazilian', 'São Paulo',
    'Las Vegas', 'Qatar', 'Abu Dhabi', 'Emilia Romagna', 'Malaysian',
], ['bahrain', 'jeddah', 'albert_park', 'shanghai', 'suzuka', 'miami', 'villeneuve', 'monaco',
    'catalunya', 'catalunya', 'red_bull_ring', 'silverstone', 'spa', 'hungaroring', 'zandvoort', 'monza',
    'baku', 'marina_bay', 'americas', 'rodriguez', 'interlagos', 'interlagos', 'vegas', 'losail',
    'yas_marina', 'imola', 'sepang']))
LEGACY_EVENTS = {_clean(name + ' Grand Prix'): circuit for name, circuit in LEGACY_EVENTS.items()}
# Event names alone are insufficient outside these historical venue periods.
HISTORICAL_EVENTS = {_clean(name + ' Grand Prix'): (circuit, years) for name, circuit, years in [
    ('French', 'ricard', range(2018, 2023)), ('Portuguese', 'portimao', (2020, 2021)),
    ('Russian', 'sochi', range(2014, 2022)), ('Turkish', 'istanbul', (*range(2005, 2012), 2020, 2021)),
]}


def legacy_circuit(event: str) -> str | None:
    return LEGACY_EVENTS.get(_clean(event))


def _hint_circuit(hint) -> str | None:
    hint = _clean(hint)
    return next((identifier for identifier, circuit in CIRCUITS.items() if hint in
                 {_clean(identifier), _clean(circuit['circuit_name']), *[_clean(a) for a in circuit['aliases']]}), None)


def resolve_venue(year: int, event: str, *, location=None, circuit_hint=None) -> dict:
    event_key = _clean(event)
    expected = legacy_circuit(event)
    source = 'event_circuit_mapping'
    if event_key in HISTORICAL_EVENTS:
        circuit, years = HISTORICAL_EVENTS[event_key]
        if int(year) in years:
            expected, source = circuit, 'historical_event_venue_period'
    if int(year) == 2026 and event_key in {_clean('Bahrain Grand Prix'), _clean('Bahrain Grand Prix in Malaysia')}:
        expected, source = 'sepang', '2026_bahrain_venue_override'
    if int(year) >= 2026 and event_key == _clean('Spanish Grand Prix'):
        expected, source = 'madring', 'spanish_venue_since_2026'
    hints = [hint for hint in (circuit_hint, location)
             if hint is not None and str(hint).strip().lower() not in {'', 'nan', 'nat', '<na>', 'none'}]
    resolved_hints = [_hint_circuit(hint) for hint in hints]
    conflict = expected and any(identifier is not None and identifier != expected for identifier in resolved_hints)
    unknown_hint = any(identifier is None for identifier in resolved_hints)
    distinct = set(identifier for identifier in resolved_hints if identifier)
    if conflict or len(distinct) > 1 or unknown_hint:
        status, identifier = 'conflict' if conflict or len(distinct) > 1 else 'unresolved', None
    else:
        identifier = expected or next(iter(distinct), None)
        status = 'resolved' if identifier else 'unresolved'
        if not expected and identifier:
            source = 'feed_circuit_identity'
    if identifier is None:
        return {'venue_status': status, 'venue_source': source, 'circuit_id': None, 'circuit_name': None,
                'layout_id': None, 'venue_country': None, 'latitude': None, 'longitude': None,
                'race_laps': None, 'race_laps_source': 'unavailable', 'feed_location': location,
                'feed_circuit_hint': circuit_hint,
                'notes': 'Circuit unresolved or conflicting; event-name circuit priors and weather coordinates withheld.'}
    circuit = CIRCUITS[identifier]
    layout = identifier + '_gp'
    laps = circuit['race_laps']
    if identifier == 'marina_bay' and int(year) < 2023:
        layout, laps = 'marina_bay_pre_2023', 61
    elif identifier == 'marina_bay':
        layout = 'marina_bay_since_2023'
    elif identifier == 'yas_marina' and int(year) < 2021:
        layout, laps = 'yas_marina_pre_2021', 55
    elif identifier == 'yas_marina':
        layout = 'yas_marina_since_2021'
    elif identifier == 'catalunya':
        layout = 'catalunya_since_2023' if int(year) >= 2023 else 'catalunya_pre_2023'
    elif identifier == 'albert_park':
        layout = 'albert_park_since_2022' if int(year) >= 2022 else 'albert_park_pre_2022'
    return {key: value for key, value in circuit.items() if key != 'aliases'} | {
        'venue_status': status, 'venue_source': source, 'layout_id': layout, 'race_laps': laps,
        'race_laps_source': 'published_2026' if int(year) == 2026 and identifier in {'sepang', 'madring'} else 'conventional_circuit_assumption',
        'feed_location': location, 'feed_circuit_hint': circuit_hint,
        'notes': 'Circuit identity resolved; race-specific operational changes still require published overrides.'}


def venue_for_context(context: dict, *, event_data=None, session=None) -> dict:
    if isinstance(context.get('venue'), dict):
        return dict(context['venue'])
    event_data = event_data if event_data is not None else getattr(session, 'event', {})
    try:
        info = getattr(session, 'session_info', {}) or {}
    except Exception:
        info = {}
    meeting = info.get('Meeting', {})
    return resolve_venue(context.get('year', 0), context.get('event', ''),
                         location=meeting.get('Location') or event_data.get('Location'),
                         circuit_hint=meeting.get('Circuit', {}).get('ShortName'))


def event_display(context: dict) -> str:
    # Historic contexts without an archived venue keep their original identity.
    venue = context.get('venue', {})
    return str(context.get('event', '')) + (' — ' + venue['circuit_name'] if venue.get('circuit_name') else '')
