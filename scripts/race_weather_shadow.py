"""Capture a fresh race forecast and preview delayed-start sensitivity locally."""
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.app_services.beta import digest, dump_new, verified_snapshot
from src.race_weather import briefing, collect_race_weather, payload_hash
from src.race_weather_shadow import simulate_weather_windows
from src.track import load_track_profile


def create_shadow(forecast_folder: Path, destination: Path, *, sims_per_member: int = 200,
                  delay_weights: list[float] | None = None, duration_minutes: int = 120) -> Path:
    manifest = verified_snapshot(forecast_folder)
    context = manifest['context']
    features = pd.read_csv(forecast_folder / 'frozen/features.csv')
    config = json.loads((forecast_folder / 'frozen/forecast_config.json').read_text(encoding='utf-8'))
    reference = config['data']['track_profiles_path']
    # Use the original reference input if it still exists, never create a template.
    if not Path(reference).is_file():
        raise ValueError('Original track reference input is unavailable.')
    profile = load_track_profile(context['event'], reference, metadata=context)
    destination.mkdir(parents=True, exist_ok=False)
    report, raw = collect_race_weather(context['race_start_utc'], profile['latitude'], profile['longitude'],
                                      duration_minutes=duration_minutes)
    report['feature_data_cutoff_utc'] = context['data_cutoff_utc']
    report['source_snapshot_sha256'] = digest(forecast_folder / 'frozen/manifest.json')
    dump_new(destination / 'race_weather_raw.json', raw)
    dump_new(destination / 'race_weather.json', report)
    predictions = pd.DataFrame()
    metadata = {'category': 'weather_shadow_unvalidated', 'simulation_status': 'weather_unavailable'}
    if report['scenarios'] and all(len(s['members']) >= 2 and all(m['simulation_usable'] for m in s['members']) for s in report['scenarios']):
        predictions, metadata = simulate_weather_windows(features, report, sims_per_member=sims_per_member,
            seed=config['run']['random_seed'], overtaking_difficulty=profile['overtaking_difficulty'],
            delay_weights=delay_weights)
        predictions.to_csv(destination / 'scenario_predictions.csv', index=False)
        metadata['simulation_status'] = 'completed'
    elif delay_weights is not None:
        raise ValueError('Delay mixture unavailable without complete ensemble weather.')
    metadata.update(source_snapshot_sha256=report['source_snapshot_sha256'],
                    feature_data_cutoff_utc=context['data_cutoff_utc'],
                    weather_retrieved_at_utc=report['retrieved_at_utc'], weather_sha256=payload_hash(report),
                    simulation_source_sha256=digest(Path(__file__).resolve().parents[1] / 'src/simulate.py'))
    metadata['overtaking_difficulty'] = profile['overtaking_difficulty']
    metadata['venue'] = {key: profile[key] for key in ('circuit_id', 'circuit_name', 'layout_id', 'venue_status', 'latitude', 'longitude', 'profile_status')}
    metadata['experiment_source_hashes'] = {name: digest(Path(__file__).resolve().parents[1] / 'src' / name)
        for name in ('race_weather.py', 'race_weather_shadow.py', 'weather.py', 'simulate.py', 'model_config.py', 'venues.py', 'track.py')}
    dump_new(destination / 'experiment.json', metadata)
    tables = []
    for scenario in report['scenarios']:
        rain = scenario['wet_hour_frequency']
        text = 'unknown' if rain is None else f'{rain:.1%}'
        label = 'Scheduled' if scenario['delay_minutes'] == 0 else f"+{scenario['delay_minutes']} min"
        def number(value):
            return 'unknown' if value is None else f'{value:.1f}'
        rain_range = ' / '.join(number(scenario[key]) for key in ('rain_mm_p10', 'rain_mm_p50', 'rain_mm_p90'))
        pre = scenario['pre_start_heavy_hour_frequency']
        pre_text = 'unknown' if pre is None else f'{pre:.1%}'
        tables.append(f'<tr><td>{label}</td><td>{html.escape(scenario["start_utc"])}</td><td>{text}</td><td>{rain_range}</td><td>{pre_text}</td><td>{scenario["complete_member_count"]}/{scenario["member_count"]}</td></tr>')
    sections = []
    if not predictions.empty:
        for delay, group in predictions.groupby('delay_minutes', sort=False):
            sections.append(f'<h2>Start {html.escape(str(delay))} minutes</h2>' + group.sort_values('avg_finish').head(10)[['Driver', *['avg_finish', 'win_chance', 'podium_chance', 'dnf_chance']]].to_html(index=False, float_format=lambda n: f'{n:.3f}'))
    document = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Race weather and delayed starts</title><style>body{font:16px/1.5 system-ui;background:#202329;color:#eee;max-width:1000px;margin:40px auto;padding:0 20px}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{padding:10px;text-align:left;border-bottom:1px solid #555}h2{margin-top:35px}p{color:#ccd2da}</style>'''
    document += f'<h1>{html.escape(context["event"])} — race weather</h1><p>Weather captured {html.escape(report["retrieved_at_utc"])}. Features frozen {html.escape(context["data_cutoff_utc"])}.</p>'
    document += '<p>Unvalidated sensitivity experiment. Live predictions unchanged. Start-delay probability unavailable. Regional ensemble rain frequencies do not establish track conditions or wet tyre use.</p>'
    document += '<div style="overflow-x:auto"><table><tr><th>Conditional start</th><th>UTC start</th><th>Wet hourly interval frequency</th><th>Rain mm P10/P50/P90</th><th>Heavy rain in preceding 2h</th><th>Complete members</th></tr>' + ''.join(tables) + '</table></div>'
    document += '<p>Two-hour race window; full race distance. Each hourly interval exceeding 0.1 mm and overlapping the window counts as wet. Sub-hour rainfall timing and race-control selection are unresolved.</p>'
    document += ''.join(sections) + '<h2>Limits</h2><ul>' + ''.join(f'<li>{html.escape(line)}</li>' for line in [*report['limitations'], *metadata.get('limitations', [])]) + '</ul></html>'
    path = destination / 'preview.html'
    path.write_text(document, encoding='utf-8')
    print(briefing(report))
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecast-folder', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--sims-per-member', type=int, default=200)
    parser.add_argument('--duration-minutes', type=int, default=120)
    parser.add_argument('--delay-weights', nargs=4, type=float, help='Explicit unvalidated assumptions for 0/30/60/120 minute starts; must sum to one.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = args.forecast_folder if args.forecast_folder.is_absolute() else root / args.forecast_folder
    destination = args.output_dir or root / 'outputs/race_weather_shadow' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    if not destination.is_absolute():
        destination = root / destination
    print(create_shadow(source, destination, sims_per_member=args.sims_per_member,
                        delay_weights=args.delay_weights, duration_minutes=args.duration_minutes))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
