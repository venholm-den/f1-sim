"""Replay saved, hash-checked inputs with expanding chronological training."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.stage_ensemble import (COMPONENTS, FORECAST_COLUMNS, STAGES, MIN_RACES,
    MIN_COVERAGE, RANK_NOISE, Episode, build_components, fit_weights,
    fit_calibration, blend, metrics, validate_forecast)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump_new(path, payload):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)


def load_episodes(predictions, results, practice, *, n_sims=20_000):
    """Collapse Monte Carlo seeds before fitting; complete races are the units."""
    p = predictions[predictions.variant.eq('legacy')].copy()
    required = {'year','round','session','event','seed','Driver','actual_position','actual_dnf',
                'grid_source','grid_position','dnf_chance',*FORECAST_COLUMNS}
    if not required.issubset(p) or p.empty:
        raise ValueError('Complete legacy prediction rows and outcome labels are required.')
    keys = ['year','round','session','Driver']
    if p.duplicated(keys+['seed']).any():
        raise ValueError('Duplicate driver/seed prediction rows.')
    # Losing one driver or one seed must not silently change the field average.
    for _, race in p.groupby(['year','round','session']):
        if race.groupby('seed').Driver.apply(lambda s:tuple(sorted(s))).nunique() != 1:
            raise ValueError('Driver coverage differs between seeds.')
    if (p.groupby(keys)[['actual_position','actual_dnf','grid_position','grid_source','event']]
            .nunique(dropna=False) > 1).any().any():
        raise ValueError('Labels or input context differ between repeated seeds.')
    columns = {name:'mean' for name in [*FORECAST_COLUMNS,'dnf_chance']}
    columns.update({name:'first' for name in ['event','actual_position','actual_dnf','grid_position','grid_source']})
    p = p.groupby(keys, as_index=False).agg(columns)
    episodes = []
    for (year, rnd, stage), frame in p.groupby(['year','round','session'], sort=True):
        if stage not in STAGES:
            continue
        frame = frame.sort_values('Driver')
        actual = frame.actual_position.to_numpy(float)
        if sorted(actual) != list(range(1,len(frame)+1)):
            raise ValueError('Scoring requires a complete, unique classification.')
        target = results[results.Year.eq(year) & results.Round.eq(rnd)]
        if target.DriverCode.duplicated().any() or set(target.DriverCode) != set(frame.Driver):
            raise ValueError(f'Outcome archive coverage differs for {year}/{rnd}.')
        labels = frame.Driver.map(target.set_index('DriverCode').Position).to_numpy(float)
        if not np.array_equal(actual, labels):
            raise ValueError(f'Archived and saved outcome labels differ for {year}/{rnd}.')
        drivers, components, dnf, availability = build_components(frame, (int(year),int(rnd)),
            stage, results, practice, n_sims=n_sims)
        episodes.append(Episode((int(year),int(rnd)), stage, frame.event.iloc[0], drivers,
            components, actual, dnf, frame.actual_dnf.to_numpy(float), availability))
    return sorted(episodes, key=lambda e:(e.key,e.stage))


def run_walk_forward(episodes):
    episodes = sorted(episodes, key=lambda e:(e.key,e.stage))
    race_metrics, predictions, fits, calibration_history = [], [], [], []
    for episode in episodes:
        weights, fit = fit_weights(episodes, episode.stage, episode.key)
        raw = blend(episode.components, weights)
        alpha, calibration = fit_calibration(calibration_history, episode.stage, episode.key)
        calibrated = blend(episode.components, weights, alpha)
        fit.update(year=episode.key[0], round=episode.key[1], session=episode.stage,
                   availability=episode.availability, calibration=calibration)
        fits.append(fit)
        variants = {'simulation':episode.components[0], 'learned_blend':raw,
                    'calibrated_blend':calibrated}
        for i, name in enumerate(COMPONENTS[1:], 1):
            if episode.availability[name]['available']:
                variants[name+'_component'] = episode.components[i]
        if episode.availability['qualifying']['available']:
            # Pure qualifying order benchmark without artificial probability noise.
            grid = np.asarray(episode.availability['qualifying']['classification'])
            variants['qualifying_order'] = validate_forecast(np.column_stack(
                [grid,grid<=1,grid<=3,grid<=10]))
        for variant, forecast in variants.items():
            record = {'year':episode.key[0], 'round':episode.key[1], 'event':episode.event,
                      'session':episode.stage, 'variant':variant,
                      'weights_fitted':fit['status']=='fitted',
                      'calibration_fitted':calibration['status']=='fitted',
                      **metrics(forecast, episode.actual, episode.dnf, episode.actual_dnf)}
            race_metrics.append(record)
            table = pd.DataFrame(forecast, columns=FORECAST_COLUMNS)
            table['Driver'] = episode.drivers
            for name in ('year','round','event','session','variant','weights_fitted','calibration_fitted'):
                table[name] = record[name]
            table['actual_position'] = episode.actual
            table['dnf_chance'] = episode.dnf
            table['actual_dnf'] = episode.actual_dnf
            predictions.extend(table.to_dict('records'))
        # Prequential predictions, not in-sample outputs. Warm-up fallback outputs
        # are excluded from calibrator training, even though their outcomes exist.
        if fit['status']=='fitted':
            calibration_history.append({'key':episode.key, 'stage':episode.stage,
                'prediction':raw, 'actual':episode.actual})
    artifact_stages = {}
    after = (9999,999)
    for stage in STAGES:
        _, fitted = fit_weights(episodes, stage, after)
        _, calibrated = fit_calibration(calibration_history, stage, after)
        artifact_stages[stage] = {**fitted, 'calibration':calibrated}
    return pd.DataFrame(race_metrics), pd.DataFrame(predictions), fits, artifact_stages


def reliability_bins(predictions):
    rows = []
    for scope, mask in [('all', np.ones(len(predictions),bool)),
                        ('weights_fitted', predictions.weights_fitted)]:
        for (stage, variant), frame in predictions[mask].groupby(['session','variant']):
            for column, threshold in [('win_chance',1),('podium_chance',3),('points_chance',10)]:
                frame = frame.copy()
                frame['bin'] = np.minimum((frame[column]*10).astype(int),9)
                for bucket, group in frame.groupby('bin'):
                    rows.append({'scope':scope, 'session':stage, 'variant':variant,
                        'event':column, 'bin_lower':bucket/10, 'drivers':len(group),
                        'races':len(group[['year','round']].drop_duplicates()),
                        'predicted':group[column].mean(),
                        'observed':group.actual_position.le(threshold).mean()})
    return pd.DataFrame(rows)


def paired_comparisons(race_metrics):
    rows = []
    columns = ['finish_mae','win_brier','podium_brier','top10_brier','loss']
    for scope, mask in [('weights_fitted',race_metrics.weights_fitted),
                        ('calibration_fitted',race_metrics.calibration_fitted)]:
        for stage, group in race_metrics[mask].groupby('session'):
            for candidate in ('learned_blend','calibrated_blend'):
                for comparator in ('simulation','qualifying_order'):
                    paired = group[group.variant.eq(candidate)].merge(
                        group[group.variant.eq(comparator)], on=['year','round'],suffixes=('_candidate','_baseline'))
                    if paired.empty:
                        continue
                    delta = (paired.finish_mae_candidate-paired.finish_mae_baseline).to_numpy()
                    rng = np.random.default_rng(12051)
                    samples = rng.choice(delta,(5000,len(delta)),replace=True).mean(axis=1)
                    row = {'scope':scope,'session':stage,'candidate':candidate,'comparator':comparator,
                           'races':len(paired),'race_keys':json.dumps(paired[['year','round']].values.tolist()),
                           'finish_delta_ci_low':float(np.quantile(samples,.025)) if len(delta)>1 else None,
                           'finish_delta_ci_high':float(np.quantile(samples,.975)) if len(delta)>1 else None}
                    for metric in columns:
                        row[metric+'_candidate'] = float(paired[metric+'_candidate'].mean())
                        row[metric+'_baseline'] = float(paired[metric+'_baseline'].mean())
                        row[metric+'_delta'] = row[metric+'_candidate']-row[metric+'_baseline']
                    rows.append(row)
    return pd.DataFrame(rows)


def benchmark(source_report, dataset, output, *, n_sims=20_000):
    source_report, dataset, output = map(Path, (source_report,dataset,output))
    source = json.loads(source_report.read_text(encoding='utf-8'))
    prediction_path = source_report.parent/'predictions.csv'
    if source.get('artifact_sha256',{}).get('predictions.csv') != digest(prediction_path):
        raise ValueError('Saved benchmark prediction checksum differs; refusing to fit.')
    results_path, practice_path = dataset/'retirement_records.csv', dataset/'practice_features.csv'
    results, practice = pd.read_csv(results_path), pd.read_csv(practice_path)
    episodes = load_episodes(pd.read_csv(prediction_path), results, practice, n_sims=n_sims)
    race_metrics, predictions, fits, stages = run_walk_forward(episodes)
    output.mkdir(parents=True, exist_ok=False)
    summaries = []
    metric_columns = ['finish_mae','win_brier','podium_brier','top10_brier','dnf_brier','loss']
    for scope, mask in [('all',np.ones(len(race_metrics),bool)),
                        ('weights_fitted',race_metrics.weights_fitted),
                        ('calibration_fitted',race_metrics.calibration_fitted)]:
        for (stage, variant), group in race_metrics[mask].groupby(['session','variant']):
            summaries.append({'scope':scope,'session':stage,'variant':variant,'races':len(group),
                              **{m:float(group[m].mean()) for m in metric_columns}})
    summary = pd.DataFrame(summaries)
    paired = paired_comparisons(race_metrics)
    for name, frame in [('race_metrics',race_metrics),('predictions',predictions),('summary',summary),
                        ('paired_comparisons',paired),('calibration_bins',reliability_bins(predictions))]:
        frame.to_csv(output/f'{name}.csv', index=False)
    dump_new(output/'walk_forward_fits.json', fits)
    assumptions = {'minimum_fit_races':MIN_RACES, 'minimum_component_coverage':MIN_COVERAGE,
        'rank_noise_positions':RANK_NOISE, 'component_simulations':n_sims,
        'component_seed':314159, 'recent_form_max_races':5, 'weight_prior':'simulation only',
        'weight_regularization':0.10, 'maximum_uniform_mass':0.35,
        'calibration_regularization':0.01, 'training_loss':'finish MAE + top10 Brier'}
    artifact = {'schema_version':1, 'model':'stage_ensemble_v1', 'activated':False,
        'promotion_approved':False, 'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'status':'shadow_only', 'stages':stages, 'assumptions':assumptions,
        'calibration_policy':'comparison_only',
        'input_sha256':{str(p.resolve()):digest(p) for p in [source_report,prediction_path,results_path,practice_path]},
        'source_sha256':{p.name:digest(p) for p in [Path(__file__),Path(__file__).with_name('stage_ensemble.py')]}}
    dump_new(output/'candidate.json',artifact)
    limitations = [
        'All source races were inspected before this experiment: no fresh promotion evidence.',
        'Expanding race/stage splits prohibit fitting to target or future outcomes; seeds are averaged first.',
        'Retrospective archive corrections are possible; historical publication timing is not established.',
        'Qualifying classification excludes later penalties; PRE and FP2 cannot use qualifying.',
        'Practice is timestamp-filtered FP2 only, with unobserved fuel and incomplete field coverage.',
        'Rank noise is a declared assumption. Missing components fall back to the simulation.',
        'DNF probabilities are unchanged; no reliability improvement is claimed.',
        'Calibration uses earlier out-of-sample blends; few races may leave it inactive.',
        'Stages and coverage differ. Compare variants only on the same paired race subset.',
        'Live activation requires at least six fresh races per stage, 5% lower loss than simulation, '
        'no Brier regression, and explicit review; Q should also beat qualifying finish MAE.']
    report = {'schema_version':1,'created_at_utc':artifact['created_at_utc'],
        'evaluated_races':[list(key) for key in sorted({e.key for e in episodes})],
        'race_stage_episodes':len(episodes),'fresh_validation_races':0,
        'promotion_allowed':False,'activated':False,'limitations':limitations,
        'assumptions':assumptions,'summary':summary.to_dict('records'),
        'paired_comparisons':json.loads(paired.to_json(orient='records')),
        'source_report':str(source_report.resolve()),'input_sha256':artifact['input_sha256'],
        'artifact_sha256':{p.name:digest(p) for p in sorted(output.iterdir()) if p.is_file()}}
    dump_new(output/'report.json',report)
    render_report(output, report, stages)
    return report


def render_report(output, report, stages):
    summary = pd.DataFrame(report['summary'])
    paired = pd.DataFrame(report['paired_comparisons'])
    def table(frame):
        return frame.to_html(index=False,border=0,float_format=lambda v:f'{v:.4f}')
    weights = [{'Stage':stage,'Status':values['status'], 'Training races':len(values['train_races']),
                **{k:round(v,3) for k,v in values['weights'].items()},
                'Uniform confidence mass':round(values['calibration']['uniform_mass'],3),
                'Calibration races':len(values['calibration']['calibration_races'])}
               for stage,values in stages.items()]
    body = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stage ensemble diagnostic</title><style>body{{background:#10121d;color:#edf1f7;font:16px/1.6 system-ui;margin:0}}main{{max-width:1200px;margin:40px auto;padding:24px}}h1{{font-size:36px}}p,li{{color:#bfc9db}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{padding:9px;border-bottom:1px solid #35394d;text-align:left}}.scroll{{overflow:auto}}a{{color:#8ee8d4}}.tag{{color:#f7bb78}}</style><main>
<p class="tag">EXPERIMENTAL · SHADOW ONLY · NO FRESH VALIDATION</p><h1>Learn the blend at each forecast stage</h1>
<p>{report['race_stage_episodes']} complete race/stage episodes. Each prediction uses weights fitted on earlier races only. Repeated simulation seeds count once. All historical results below are previously inspected diagnostics.</p>
<h2>Chronological evaluation after weight training</h2><p>Lower is better. Each stage uses its own paired subset; qualifying-only rows can have fewer races when a complete Q grid was unavailable.</p>
<div class="scroll">{table(summary[summary.scope.eq('weights_fitted')].drop(columns='scope'))}</div>
<h2>Comparison on identical races</h2><p>Candidate minus baseline: negative is better. Finish error intervals bootstrap complete races, not drivers or simulation seeds; small samples remain uncertain.</p>
<div class="scroll">{table(paired[paired.scope.eq('weights_fitted')][['session','candidate','comparator','races','finish_mae_candidate','finish_mae_baseline','finish_mae_delta','finish_delta_ci_low','finish_delta_ci_high']])}</div>
<h2>Confidence adjustment evaluation</h2><p>Only episodes with enough earlier out-of-sample blends to fit calibration. Uniform mass softens the whole field distribution and preserves win/podium/top-10 totals.</p>
<div class="scroll">{table(summary[summary.scope.eq('calibration_fitted')].drop(columns='scope'))}</div>
<h2>Candidate fitted for the next race</h2><div class="scroll">{table(pd.DataFrame(weights))}</div>
<h2>Limits and activation decision</h2><ul>{''.join('<li>'+html.escape(x)+'</li>' for x in report['limitations'])}</ul>
<p><a href="candidate.json">Inactive candidate</a> · <a href="walk_forward_fits.json">Every training cutoff and weight</a> · <a href="race_metrics.csv">Paired race metrics</a> · <a href="calibration_bins.csv">Reliability bins</a> · <a href="report.json">Provenance</a></p></main></html>'''
    (output/'report.html').write_text(body,encoding='utf-8')
