"""Data-derived Discord cards. Rendering never loads credentials or posts messages."""
from __future__ import annotations

import math
import textwrap
from functools import lru_cache
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

W, H = 1600, 1280
BG, PANEL, LINE = '#10141C', '#1A202B', '#303947'
WHITE, MUTED = '#F3F5F7', '#A9B5C5'
RED, CYAN, LIME, ORANGE = '#FF5B65', '#67DCE5', '#C8F36B', '#FFAC63'


@lru_cache(maxsize=64)
def _font(size, symbols=False):
    # Segoe supports the arrows missing from Bahnschrift. Matplotlib supplies
    # a portable fallback on Linux and in existing packaged distributions.
    windows = Path('C:/Windows/Fonts/segoeui.ttf' if symbols else 'C:/Windows/Fonts/bahnschrift.ttf')
    if windows.is_file():
        return ImageFont.truetype(str(windows), size)
    from matplotlib import get_data_path
    return ImageFont.truetype(str(Path(get_data_path()) / 'fonts/ttf/DejaVuSans.ttf'), size)


def text(draw, xy, value, size=32, fill=WHITE, anchor=None, width=None):
    value = str(value).replace('\n', ' ')
    symbols = '→' in value
    if width:
        while size > 20 and draw.textlength(value, font=_font(size, symbols)) > width:
            size -= 1
        while value and draw.textlength(value, font=_font(size, symbols)) > width:
            value = value[:-2].rstrip('…') + '…'
    draw.text(xy, value, font=_font(size, symbols), fill=fill, anchor=anchor)


def number(value):
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (ValueError, TypeError):
        return None


def probability(value):
    value = number(value)
    if value is None or not 0 <= value <= 1:
        return 'Unavailable'
    return '<0.1%' if 0 < value < .001 else f'{value:.1%}'


def position(value):
    value = number(value)
    return f'P{value:g}' if value is not None and value > 0 else 'Unavailable'


def panel(draw, box):
    draw.rounded_rectangle(box, radius=18, fill=PANEL)


def base(kicker, title, subtitle, footer, accent=CYAN):
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)
    for x in range(930, 1800, 90):
        d.line((x, 0, x - 240, 230), fill='#171E28', width=2)
    d.rectangle((0, 0, W, 10), fill=accent)
    text(d, (64, 48), 'F1 SIM  /  RACE INTELLIGENCE', 28, accent)
    text(d, (1536, 48), kicker, 28, MUTED, 'ra', width=780)
    text(d, (64, 106), title, 88, width=1472)
    text(d, (64, 222), subtitle, 32, MUTED, width=1472)
    for y in (280, 1156):
        d.line((64, y, 1536, y), fill=LINE, width=2)
    text(d, (64, 1180), footer, 26, MUTED, width=1472)
    text(d, (64, 1222), 'EXPERIMENTAL MODEL  /  PROBABILITIES ARE NOT GUARANTEES', 24, MUTED)
    return img, d


def stat(d, x, label, value, note, color=WHITE):
    panel(d, (x, 312, x + 472, 494))
    text(d, (x + 26, 334), label, 27, MUTED, width=420)
    text(d, (x + 26, 374), value, 60, color, width=420)
    text(d, (x + 26, 452), note, 26, MUTED, width=420)


def save(img, destination, name):
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / name
    img.save(path, optimize=True)
    return path


def _forecast_base(manifest, title, subtitle, accent=CYAN):
    c = manifest['context']
    stamp = pd.Timestamp(manifest['created_at_utc']).strftime('%d %b %Y, %H:%M UTC')
    return base(f"{c['event']} {c['year']} / {c['session']}", title, subtitle,
                f'Snapshot: {stamp}  |  Frozen before sharing', accent)


def outlook_card(data, manifest, destination):
    has_win = 'win_chance' in data and data.win_chance.notna().any()
    leaders = data.sort_values('win_chance' if has_win else 'avg_finish', ascending=not has_win).head(5)
    venue = manifest['context'].get('venue', {}).get('circuit_name') or manifest['context']['event']
    img, d = _forecast_base(manifest, 'THE RACE OUTLOOK', venue)
    for i, row in enumerate(leaders.head(2).itertuples()):
        value = probability(getattr(row, 'win_chance', None)) if has_win else f'{row.avg_finish:.1f}'
        stat(d, 64 + i * 500, 'MODEL FAVOURITE' if i == 0 else 'NEXT CONTENDER',
             f'{row.Driver} {value}', 'Win probability' if has_win else 'Mean finishing position', [CYAN, ORANGE][i])
    combined = leaders.head(2).win_chance.sum() if has_win else None
    stat(d, 1064, 'TOP TWO COMBINED' if has_win else 'DRIVER COVERAGE',
         probability(combined) if has_win else str(len(data)),
         'Win probability' if has_win else 'Drivers in the frozen forecast', LIME)
    text(d, (64, 536), 'WIN PROBABILITY' if has_win else 'EXPECTED FINISH', 28, MUTED)
    if has_win:
        text(d, (1085, 540), 'Bar scale: 0–100%', 24, MUTED, 'ra')
    text(d, (1260, 536), 'PODIUM', 27, MUTED, 'ra')
    text(d, (1536, 536), 'MEAN FINISH', 27, MUTED, 'ra')
    for i, row in enumerate(leaders.itertuples()):
        y = 596 + i * 87
        color = CYAN if i == 0 else ORANGE if i == 1 else MUTED
        text(d, (64, y), row.Driver, 42, width=130)
        if has_win:
            p = number(row.win_chance)
            d.rounded_rectangle((210, y + 10, 940, y + 48), radius=7, fill=LINE)
            if p is not None and p > 0:
                d.rounded_rectangle((210, y + 10, 210 + max(2, 730 * p), y + 48), radius=7, fill=color)
            text(d, (1085, y), probability(row.win_chance), 40, color, 'ra')
        text(d, (1260, y + 3), probability(getattr(row, 'podium_chance', None)), 34, WHITE, 'ra')
        text(d, (1536, y + 3), f'{row.avg_finish:.1f}', 36, WHITE, 'ra')
    rounds = pd.to_numeric(leaders.get('baseline_rounds', pd.Series(dtype=float)), errors='coerce').dropna()
    history = (str(int(rounds.min())) if rounds.min() == rounds.max()
               else f'{int(rounds.min())}–{int(rounds.max())}') if not rounds.empty else None
    note = (f'EVIDENCE: leading-driver pace history draws on {history} recent races.'
            if history is not None else 'EVIDENCE: historical coverage unavailable in this frozen summary.')
    panel(d, (64, 1064, 1536, 1130))
    text(d, (88, 1080), note, 29, MUTED, width=1420)
    return save(img, destination, 'race_outlook.png')


def points_card(data, manifest, destination):
    if 'points_chance' not in data:
        return None
    # Pick the genuinely uncertain points battle, not the top four favourites.
    ranked = data.loc[pd.to_numeric(data.points_chance, errors='coerce').between(0, 1)].copy()
    ranked['distance'] = (ranked.points_chance - .5).abs()
    selected = ranked.sort_values(['distance', 'Driver']).head(4).sort_values('points_chance', ascending=False)
    if selected.empty:
        return None
    img, d = _forecast_base(manifest, 'THE FIGHT FOR POINTS',
                            'Drivers closest to the top-10 probability boundary', LIME)
    for i, row in enumerate(selected.itertuples()):
        x, y = 64 + i % 2 * 750, 316 + i // 2 * 370
        panel(d, (x, y, x + 722, y + 342))
        text(d, (x + 28, y + 22), row.Driver, 55, width=240)
        text(d, (x + 692, y + 33), f'GRID {position(getattr(row, "grid_position", None))}', 29, MUTED, 'ra')
        color = LIME if i == 0 else CYAN
        text(d, (x + 28, y + 98), probability(row.points_chance), 93, color)
        text(d, (x + 28, y + 208), 'chance of finishing in the top 10', 30, MUTED)
        d.rounded_rectangle((x + 28, y + 264, x + 692, y + 277), radius=6, fill=LINE)
        if row.points_chance > 0:
            d.rounded_rectangle((x + 28, y + 264, x + 28 + max(2, 664 * row.points_chance), y + 277), radius=6, fill=color)
        low, high = number(getattr(row, 'finish_p25', None)), number(getattr(row, 'finish_p75', None))
        label = f'Middle 50% of simulations: {position(low)}–{position(high)}' if low is not None and high is not None else 'Simulated finish range unavailable'
        text(d, (x + 28, y + 296), label, 28, width=666)
    text(d, (64, 1086), 'Ranges describe simulated outcomes; actual finishes can fall outside them.', 30, MUTED, width=1472)
    return save(img, destination, 'points_battle.png')


def revision_card(data, earlier, manifest, previous, destination):
    if (data.Driver.duplicated().any() or earlier.Driver.duplicated().any()
            or set(data.Driver) != set(earlier.Driver) or 'win_chance' not in data or 'win_chance' not in earlier):
        return None
    merged = data.merge(earlier, on='Driver', suffixes=('', '_old'), validate='one_to_one')
    merged['delta'] = (merged.win_chance - merged.win_chance_old) * 100
    rows = merged.loc[merged.delta.abs().nlargest(4).index].dropna(subset=['delta'])
    if rows.empty:
        return None
    grid = manifest['context'].get('revision_reason') == 'fia_grid_update'
    img, d = _forecast_base(manifest, 'THE GRID CHANGED.' if grid else 'THE FORECAST MOVED.',
                            f"Compared with the previous {previous['context']['session']} forecast", ORANGE)
    text(d, (64, 320), 'BIGGEST WIN-PROBABILITY MOVES', 30, MUTED)
    for i, row in enumerate(rows.itertuples()):
        y = 388 + i * 154
        panel(d, (64, y, 1536, y + 132))
        text(d, (90, y + 19), row.Driver, 53, width=150)
        text(d, (275, y + 20), f'{position(getattr(row, "grid_position_old", None))} → {position(getattr(row, "grid_position", None))}', 44, width=430)
        text(d, (275, y + 77), 'Frozen grid position', 26, MUTED)
        text(d, (750, y + 21), f'{probability(row.win_chance_old)} → {probability(row.win_chance)}', 44, width=475)
        text(d, (750, y + 77), 'Modelled win probability', 26, MUTED)
        text(d, (1504, y + 20), f'{row.delta:+.2f} pp', 52, LIME if row.delta > 0 else RED, 'ra')
        text(d, (1504, y + 86), 'percentage points', 25, MUTED, 'ra')
    text(d, (64, 1040), 'WHAT THIS MEANS', 28, ORANGE)
    text(d, (64, 1082), 'Changes use unrounded values; multiple inputs/settings may contribute.', 31, MUTED, width=1472)
    return save(img, destination, 'forecast_update.png')


def render_forecast_cards(folder, destination):
    from src.app_services.beta import verified_snapshot
    from src.app_services.discord_reports import _previous_forecast
    manifest = verified_snapshot(folder)
    data = pd.read_csv(folder / 'frozen/simulation_summary.csv')
    paths = [outlook_card(data, manifest, destination)]
    points = points_card(data, manifest, destination)
    if points:
        paths.append(points)
    previous = _previous_forecast(folder, manifest)
    if previous:
        saved, earlier = previous
        update = revision_card(data, earlier, manifest, saved, destination)
        if update:
            paths.append(update)
    return paths


def render_post_race_card(folder, context, destination):
    from src.app_services.discord_reports import analysis_summary, read_json
    c = pd.read_csv(folder / 'score_comparison.csv')
    summary, metrics = analysis_summary(c), read_json(folder / 'score.json')
    stamp = metrics.get('evaluated_at_utc', '')
    footer = ('Evaluated: ' + pd.Timestamp(stamp).strftime('%d %b %Y, %H:%M UTC') if stamp else 'Evaluation timestamp unavailable')
    img, d = base(f"{context['event']} {context['year']} / POST-RACE", 'HOW DID IT HOLD UP?',
                  f"Official results vs the frozen {context['session']} forecast / {len(c)} drivers", footer, RED)
    model, grid = summary['finish_mae'], summary['grid_baseline_mae']
    delta = model - grid if grid is not None else None
    stat(d, 64, 'MODEL FINISH ERROR', f'{model:.2f}', 'Places · mean absolute error')
    stat(d, 564, 'FROZEN-GRID BASELINE', f'{grid:.2f}' if grid is not None else 'Unavailable', 'Places · lower is better', CYAN)
    stat(d, 1064, 'MODEL VS BASELINE', f'{delta:+.2f}' if delta is not None else 'Unavailable',
         'Places · negative is better', LIME if delta is not None and delta < 0 else RED)
    panel(d, (64, 530, 1536, 675))
    text(d, (94, 548), 'VERDICT', 28, RED)
    verdict = ('Baseline comparison unavailable: complete frozen grid required.' if delta is None else
               'The model beat the simple grid baseline.' if delta < -.005 else
               'The model missed the simple grid baseline.' if delta > .005 else 'The model matched the simple grid baseline.')
    text(d, (94, 593), verdict, 49, width=1400)
    text(d, (64, 724), 'OUTCOME-RANGE CHECK', 29, MUTED)
    valid = pd.Series(False, index=c.index)
    if {'finish_p25', 'finish_p75'}.issubset(c.columns):
        low, high = pd.to_numeric(c.finish_p25, errors='coerce'), pd.to_numeric(c.finish_p75, errors='coerce')
        valid = low.notna() & high.notna() & low.le(high)
        inside = c.actual_position.between(low, high) & valid
    count, total = int(inside.sum()) if valid.any() else 0, int(valid.sum())
    text(d, (64, 774), f'{count} / {total}' if total else 'N/A', 98, ORANGE)
    text(d, (465, 795), 'actual finishes inside the model’s', 38)
    text(d, (465, 847), 'middle-50% simulated ranges', 38)
    if total:
        step = min(66, 1460 / total)
        for i in range(total):
            x = 65 + i * step
            d.rounded_rectangle((x, 935, x + step * .73, 982), radius=6, fill=ORANGE if i < count else LINE)
    text(d, (64, 1006), f'Aggregate coverage: {total}/{len(c)} drivers have valid saved ranges.', 28, MUTED)
    text(d, (64, 1090), 'One race is a diagnostic. It does not establish probability calibration.', 31, MUTED, width=1472)
    return save(img, destination, 'post_race_scorecard.png')


def render_weekend_card(briefing, destination):
    sessions, track = briefing['sessions'], briefing['track']
    captured = pd.Timestamp(briefing['captured_at_utc']).strftime('%d %b %Y, %H:%M UTC')
    img, d = base(f"ROUND {briefing['round']} / {briefing['year']}", 'YOUR RACE WEEKEND',
                  briefing['event'], f"Schedule captured: {captured} / Times: Europe/London", CYAN)
    text(d, (64, 320), 'F1 SESSION STARTS · UK TIME', 30, CYAN)
    for i, session in enumerate(sessions):
        y = 382 + i * 128
        panel(d, (64, y, 922, y + 108))
        text(d, (88, y + 14), session['name'], 37, width=470)
        text(d, (88, y + 62), session['uk_date'], 26, MUTED)
        text(d, (896, y + 25), session['uk_time'], 43, LIME if session['code'] == 'R' else WHITE, 'ra')
    panel(d, (954, 316, 1536, 1060))
    text(d, (982, 338), 'THE TRACK', 28, CYAN)
    for i, line in enumerate(textwrap.wrap(track.get('circuit_name') or 'Circuit unresolved', 23)):
        text(d, (982, 384 + i * 48), line, 39, width=526)
    details = [('COUNTRY', track.get('venue_country') or 'Unavailable'),
               ('WEEKEND FORMAT', briefing['format']),
               ('REFERENCE RACE LAPS', str(track.get('race_laps') or 'Unavailable')),
               ('REFERENCE LAP LENGTH', f"{track['length_km']:.3f} km" if track.get('length_km') else 'Unavailable')]
    for i, (label, value) in enumerate(details):
        y = 535 + i * 111
        text(d, (982, y), label, 24, MUTED)
        text(d, (982, y + 37), value, 37, width=526)
    text(d, (982, 1000), track.get('reference_label', 'Track reference unavailable'), 23, MUTED, width=526)
    text(d, (64, 1090), 'Published session starts may change. Track figures are reference data.', 31, MUTED, width=1472)
    # This is a schedule, not a simulation forecast.
    d.rectangle((64, 1218, 1536, 1270), fill=BG)
    text(d, (64, 1222), 'FASTF1 CALENDAR  /  UK TIMES INCLUDE GMT/BST AUTOMATICALLY', 24, MUTED)
    return save(img, destination, 'weekend_briefing.png')
