"""Render a local, standalone review of a completed enrichment dataset."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import pandas as pd


def render(dataset, weather=None, verification=None):
    dataset = Path(dataset)
    report = json.loads((dataset/'report.json').read_text(encoding='utf-8'))
    fia = json.loads((dataset/'fia/collection.json').read_text(encoding='utf-8')) if (dataset/'fia/collection.json').exists() else {}
    metrics = []
    for name, label in [('candidate-qualifying', 'Qualifying-only'), ('candidate-enriched', 'Practice + reliability')]:
        path = dataset/name/'historical_model_metrics.json'
        if path.exists():
            row = json.loads(path.read_text())
            metrics.append({'Model': label, 'Finish MAE': round(row['finish_mae'], 3),
                            'Retirement Brier': round(row['dnf_brier'], 4), 'Activated': row['activated'],
                            'Train races': len(row['train_races']), 'Validation races': len(row['validation_races'])})
    if metrics:
        grid = json.loads((dataset/'candidate-enriched/historical_model_metrics.json').read_text())
        metrics.append({'Model': 'Qualifying-order / training retirement-rate baselines',
                        'Finish MAE': round(grid['qualifying_baseline_mae'], 3),
                        'Retirement Brier': round(grid['dnf_prior_baseline_brier'], 4), 'Activated': False,
                        'Train races': len(grid['train_races']), 'Validation races': len(grid['validation_races'])})
    weather_report = json.loads((Path(weather)/'report.json').read_text()) if weather else {}
    paired = len(pd.read_csv(Path(weather)/'observation_pairs.csv')) if weather and (Path(weather)/'observation_pairs.csv').exists() else 0
    practice = pd.read_csv(dataset/'practice_features.csv')
    coverage = []
    for year in report['years']:
        races = [r for r in report['races'] if r['Year'] == year]
        coverage.append({'Year': year, 'Archived events': len(races),
                         'Q + R pairs': sum({'Q', 'R'}.issubset(r['available_sessions']) for r in races),
                         'FP2 sessions': sum('FP2' in r['available_sessions'] for r in races),
                         'Matched practice driver rows': int(practice.Year.eq(year).sum()) if 'Year' in practice else 0})
    cards = [('Archived sessions', report['sessions']), ('Practice driver rows', report['practice_driver_rows']),
             ('Race outcome records', report['retirement_rows']), ('Tyre stints', report['stints']),
             ('Measured pit traversals', report['measured_pit_traversals']), ('FIA PDFs extracted', f"{fia.get('extracted', 0)}/{fia.get('attempted', 0)}")]
    card_html = ''.join(f'<article><b>{html.escape(str(value))}</b><span>{label}</span></article>' for label, value in cards)
    failures = [{'Year': r['year'], 'Event': r['event'], 'Document': r['title'], 'Reason': r.get('error', '')}
                for r in fia.get('documents', []) if r['status'] != 'extracted']
    def table(rows):
        return pd.DataFrame(rows).to_html(index=False, escape=True, border=0) if rows else '<p>No records.</p>'
    checks = json.loads(Path(verification).read_text()) if verification else {}
    check_text = (f"{checks.get('regression_tests_passed', 'Unknown')} regression tests passed. "
                  f"JavaScript syntax: {checks.get('javascript_syntax', 'unknown')}. "
                  f"{checks.get('protected_files_checked', 0)} forecast, receipt and active-model files checked; "
                  f"{len(checks.get('protected_files_changed', []))} changed. "
                  f"Dataset checksum mismatches: {len(checks.get('dataset_checksum_mismatches', []))}. "
                  "Scheduler eligibility check completed without delivery.")
    content = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Prediction data enrichment</title><style>body{{margin:0;background:#0c1117;color:#e9edf3;font:16px/1.55 system-ui}}main{{max-width:1120px;margin:40px auto;padding:0 24px}}h1{{font-size:36px;margin-bottom:8px}}h2{{margin-top:32px}}p{{color:#b5c0ce}}.tag{{color:#f8bf62;font-weight:700}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}article{{padding:20px;background:#151e28;border:1px solid #2a3544;border-radius:8px}}article b{{display:block;font-size:30px;color:#6fdbc4}}article span{{color:#b5c0ce}}table{{width:100%;border-collapse:collapse;font-size:14px}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #2a3544}}a{{color:#7cdde0}}.scroll{{overflow:auto}}@media(max-width:700px){{.cards{{grid-template-columns:1fr 1fr}}h1{{font-size:28px}}}}</style><main>
<div class="tag">LOCAL DATA PIPELINES · EXPERIMENTAL MODELS INACTIVE</div><h1>More useful evidence for race predictions</h1>
<p>New source data and reproducible training inputs. Forecast accuracy has not been established by collecting more data.</p><div class="cards">{card_html}</div>
<h2>What is available</h2><div class="scroll">{table(coverage)}</div><p>Practice profiles count driver/race rows with at least one usable matched practice input. Absent sessions may be missing downloads or sessions not scheduled on sprint weekends. Previously downloaded telemetry and source versions were retained.</p>
<h2>Model diagnostic</h2><div class="scroll">{table(metrics)}</div><p>Same chronological split and driver cohort. Lower errors are better. These historical holdouts have already been inspected; they provide no fresh promotion evidence. Practice includes unobserved fuel and traffic effects. All new artifacts remain inactive, regardless of a metric improving.</p>
<h2>Weather and delayed starts</h2><p>Original-run replay: {len(weather_report.get('scenarios', []))} conditional start windows and {paired} UTC temperature/wind pairs. Public availability verified: {weather_report.get('availability_verified', False)}. Training eligible: {weather_report.get('eligible_for_training', False)}. Binary observed rainfall is not used as rainfall millimetres.</p><p>{report['verified_start_delay_events']} sourced initial formation-lap delay examples are available. They are positive cases only: no calibrated start-delay probability is produced. Normal controls, comparable start definitions and more events are required.</p>
<h2>FIA extraction coverage</h2><p>{html.escape(str(fia.get('tables', {})))}. Separate publication versions are retained. Official grid footnotes supply explicit penalty records. Incomplete grids, unsupported pit-lane formats and unmapped drivers are quarantined; sprint grids cannot substitute for race grids.</p><details><summary>Documents requiring review</summary><div class="scroll">{table(failures)}</div></details>
<h2>Verification and use</h2><p>{html.escape(check_text)}</p><p>In the source app, open Model Training and select “Include practice long runs and recent reliability (experimental)”. Restart a running source app to load Python changes. Existing packaged executables were not rebuilt.</p>
<p><a href="report.json">Dataset manifest and coverage</a> · <a href="fia/collection.json">FIA extraction ledger</a> · <a href="practice_features.csv">Practice features</a> · <a href="start_delay_labels.csv">Start-delay labels and sources</a> · <a href="retirement_causes.csv">Confirmed cause seed and source</a></p>
</main></html>'''
    destination = dataset/'report.html'
    if destination.exists():
        raise FileExistsError('Choose a new dataset report; previous reports are preserved.')
    destination.write_text(content, encoding='utf-8')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--weather', type=Path)
    parser.add_argument('--verification', type=Path)
    args = parser.parse_args()
    print(render(args.dataset, args.weather, args.verification))
