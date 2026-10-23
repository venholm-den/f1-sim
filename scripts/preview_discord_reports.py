"""Render existing runs as local Discord previews without posting or changing them."""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from src.app_services.beta import digest, verified_snapshot
from src.app_services.discord_reports import forecast_message, message_text, read_json
from src.app_services.discord_cards import render_forecast_cards
from src.app_services.post_race_automation import render_analysis


def _markup(value: str) -> str:
    escaped = html.escape(value)
    escaped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)

    def timestamp(match):
        value = datetime.fromtimestamp(int(match.group(1)), timezone.utc)
        return value.strftime('%d %b %Y, %H:%M UTC') if match.group(2) == 'f' else 'age shown in Discord'

    escaped = re.sub(r'&lt;t:(\d+):([fR])&gt;', timestamp, escaped)
    return escaped.replace('\n', '<br>')


def _card(payload: dict, images: list[str]) -> str:
    embed = payload['embeds'][0]
    fields = ''.join(f"<div class='field'><h3>{html.escape(field['name'])}</h3><p>{_markup(field['value'])}</p></div>"
                     for field in embed['fields'])
    charts = ''.join(f"<a href='{html.escape(path)}'><img alt='Report chart' src='{html.escape(path)}'></a>" for path in images)
    return (f"<section style='--accent:#{embed['color']:06x}'><h2>{html.escape(embed['title'])}</h2>"
            f"<p>{_markup(embed.get('description', ''))}</p>{fields}"
            f"<footer>{html.escape(embed['footer']['text'])}</footer>{charts}</section>")


def create_preview(root: Path, forecast_id: str, score_id: str, destination: Path) -> Path:
    run_root = root / 'outputs/app_runs'
    # IDs are directory names rather than arbitrary paths supplied on the command line.
    if any(not re.fullmatch(r'[0-9T_Z-]+_[a-f0-9]{8}', value) for value in (forecast_id, score_id)):
        raise ValueError('Choose forecast and score job IDs from outputs/app_runs.')
    source = run_root / forecast_id
    score = run_root / score_id
    manifest = verified_snapshot(source)
    if read_json(score / 'score.json').get('snapshot_sha256') != digest(source / 'frozen/manifest.json'):
        raise ValueError('The selected score belongs to a different frozen forecast.')
    destination.mkdir(parents=True, exist_ok=False)
    forecast_dir = destination / 'forecast'
    score_dir = destination / 'post_race'
    forecast_dir.mkdir()
    score_dir.mkdir()
    payload = forecast_message(source)
    (forecast_dir / 'payload.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
    (forecast_dir / 'summary.md').write_text(message_text(payload), encoding='utf-8')
    charts = render_forecast_cards(source, forecast_dir)
    for name in ('score.json', 'score_comparison.csv', 'actual_results.csv'):
        shutil.copy2(score / name, score_dir / name)
    render_analysis(score_dir, manifest['context'], history_root=run_root)
    post_race = read_json(score_dir / 'post_race_embed.json')
    cards = _card(payload, [str(path.relative_to(destination)).replace('\\', '/') for path in charts])
    cards += _card(post_race, ['post_race/post_race_scorecard.png'])
    document = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>F1 Sim Discord preview</title>
<style>
*{box-sizing:border-box}body{background:#202329;color:#ecedef;font:16px/1.5 system-ui,sans-serif;margin:0;padding:24px}
main{max-width:740px;margin:auto}h1{font-size:24px}h2{font-size:21px;color:#fff;margin:0 0 10px}
h3{font-size:15px;color:#fff;margin:0 0 5px}p{margin:0}section{background:#2b2f36;border-left:4px solid var(--accent);
padding:22px;border-radius:6px;margin:24px 0}.field{margin:19px 0}footer{font-size:12px;color:#b8bec7;margin:20px 0}
img{display:block;width:100%;height:auto;margin:16px 0;border-radius:4px}.notice{color:#b8bec7;font-size:14px}
@media(max-width:480px){body{padding:12px}section{padding:16px}h2{font-size:19px}}
</style><main><h1>F1 Sim — Discord output preview</h1>
<p class="notice">Local preview from existing frozen outputs. No messages sent. Discord styling may differ.</p>
""" + cards + '</main></html>'
    path = destination / 'preview.html'
    path.write_text(document, encoding='utf-8')
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecast-id', required=True)
    parser.add_argument('--score-id', required=True)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = args.output_dir or root / 'outputs/discord_output_previews' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    if not destination.is_absolute():
        destination = root / destination
    print(create_preview(root, args.forecast_id, args.score_id, destination))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
