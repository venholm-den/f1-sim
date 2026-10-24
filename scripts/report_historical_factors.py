"""Render the saved factor-analysis evidence without changing model settings."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.analyse_historical_factors import bootstrap


def render(folder,followup=None):
    folder=Path(folder)
    report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    metrics=pd.read_csv(folder/'race_metrics.csv')
    features=pd.read_csv(folder/'features.csv')
    context=pd.read_csv(folder/'race_context.csv')
    years=pd.read_csv(folder/'year_scores.csv')
    anchor=metrics[metrics.variant.eq('anchor_only')][['Year','Round','mae','dnf_brier']]
    comparison=[]
    for name,group in metrics.groupby('variant'):
        pair=group.merge(anchor,on=['Year','Round'],suffixes=('','_anchor'),validate='one_to_one')
        change=pair.mae-pair.mae_anchor
        ci=bootstrap(change)
        qci=bootstrap(pair.delta)
        comparison.append(dict(variant=name,races=len(pair),mae=pair.mae.mean(),
            q_mae=pair.q_mae.mean(),change_vs_q=pair.delta.mean(),q_ci_low=qci[0],q_ci_high=qci[1],
            change_vs_anchor=change.mean(),anchor_ci_low=ci[0],anchor_ci_high=ci[1],
            dnf_brier=pair.dnf_brier.mean(),dnf_prior_brier=pair.dnf_prior_brier.mean(),
            dnf_change_vs_anchor=(pair.dnf_brier-pair.dnf_brier_anchor).mean()))
    comparison=pd.DataFrame(comparison).sort_values('mae')
    comparison.to_csv(folder/'incremental_factor_scores.csv',index=False)
    beta=[]
    for label,columns in [('driver',['prior_driver_dnf']),('team',['prior_team_dnf']),
                           ('equal_driver_team',['prior_driver_dnf','prior_team_dnf'])]:
        frame=features[features.Year.ge(2024)&features.actual_dnf.notna()].copy()
        frame['p']=frame[columns].mean(axis=1)
        values=[]
        for (year,round_),part in frame.groupby(['Year','Round']):
            base=metrics[(metrics.Year==year)&(metrics.Round==round_)].dnf_prior_brier.iloc[0]
            score=((part.p-part.actual_dnf)**2).mean()
            values.append(dict(Year=year,Round=round_,variant=label,brier=score,prior_brier=base,delta=score-base))
        beta.extend(values)
    beta=pd.DataFrame(beta);beta.to_csv(folder/'direct_reliability_scores.csv',index=False)
    beta_summary=[]
    for label,part in beta.groupby('variant'):
        ci=bootstrap(part.delta)
        beta_summary.append(dict(variant=label,races=len(part),brier=part.brier.mean(),
            prior_brier=part.prior_brier.mean(),change=part.delta.mean(),ci_low=ci[0],ci_high=ci[1]))
    beta_summary=pd.DataFrame(beta_summary)
    beta_summary.to_csv(folder/'direct_reliability_summary.csv',index=False)
    outcome=features.assign(grid_error=(features.actual_finish-features.q_rank).abs()).groupby('outcome_class').agg(
        drivers=('Year','size'),grid_mae=('grid_error','mean')).reset_index()
    outcome.to_csv(folder/'outcome_error_decomposition.csv',index=False)
    regime=context.merge(metrics[metrics.variant.eq('anchor_only')],on=['Year','Round'],suffixes=('','_metric'))
    weather=regime.groupby('actual_wet',dropna=False).agg(races=('Year','size'),grid_mae=('q_mae','mean'),
        adjusted_mae=('mae','mean')).reset_index()
    weather.to_csv(folder/'actual_weather_diagnostics.csv',index=False)
    coverage=pd.read_csv(folder/'feature_coverage.csv')
    correlations=pd.read_csv(folder/'factor_correlations.csv')
    display=comparison.sort_values('change_vs_anchor')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
    fig,axes=plt.subplots(1,2,figsize=(13,5.5),layout='constrained')
    for ax,mean,low,high,title in [(axes[0],'change_vs_q','q_ci_low','q_ci_high','Compared with qualifying order'),
                                  (axes[1],'change_vs_anchor','anchor_ci_low','anchor_ci_high','Extra value beyond a learned grid adjustment')]:
        y=np.arange(len(display))
        ax.errorbar(display[mean],y,xerr=[display[mean]-display[low],display[high]-display[mean]],
                    fmt='o',color='#166b72',capsize=3)
        ax.axvline(0,color='#b3543c',linestyle='--',linewidth=1)
        ax.set_yticks(y,display.variant.str.replace('_',' '));ax.set_title(title)
        ax.set_xlabel('Change in mean absolute finish error (positions)\nNegative is better; race-bootstrap 95% interval')
        ax.grid(axis='x',alpha=.18)
    fig.suptitle('Exploratory diagnostics: score 2024–2026 using earlier seasons only',fontsize=14)
    fig.savefig(folder/'factor_effects.png',dpi=180);plt.close(fig)
    pivot=years.pivot(index='variant',columns='Year',values='delta').reindex(comparison.variant)
    fig,ax=plt.subplots(figsize=(7,5),layout='constrained')
    image=ax.imshow(pivot.to_numpy(),cmap='RdYlGn_r',vmin=-.7,vmax=.7,aspect='auto')
    ax.set_yticks(range(len(pivot)),pivot.index.str.replace('_',' '));ax.set_xticks(range(len(pivot.columns)),pivot.columns)
    for i in range(len(pivot)):
        for j in range(len(pivot.columns)):
            ax.text(j,i,f'{pivot.iloc[i,j]:+.3f}',ha='center',va='center')
    ax.set_title('Change in finish error versus qualifying order\nEach column uses a separately fitted earlier-season model')
    fig.colorbar(image,ax=ax,label='Positions of error; negative is better')
    fig.savefig(folder/'season_stability.png',dpi=180);plt.close(fig)
    counts=features.groupby('Year').agg(driver_rows=('DriverCode','size'),races=('Round','nunique')).reset_index()
    known=features.actual_dnf.notna();retired=features.actual_dnf.eq(1)
    facts={'archive_sessions':report['sessions'],'archive_races':report['race_sessions'],
        'verified_files':report['verified_files'],'verified_bytes':report['verified_bytes'],
        'lap_rows':report['archive_lap_rows'],'car_samples':report['car_telemetry_rows'],
        'model_races':report['feature_races'],'model_rows':report['feature_rows'],
        'model_dnf_rate':float(features.loc[known,'actual_dnf'].mean()),
        'unspecified_share_of_retirements':float((features.outcome_class.eq('unspecified_dnf')&retired).sum()/retired.sum()),
        'pole_win_rate':float(features.loc[features.q_rank.eq(1),'actual_finish'].eq(1).mean()),
        'analysis_report_sha256':hashlib.sha256((folder/'report.json').read_bytes()).hexdigest(),
        'renderer_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'activated':False}
    (folder/'key_facts.json').write_text(json.dumps(facts,indent=2),encoding='utf-8')
    methods=('Fixed Ridge alpha=100 and logistic C=0.1; no parameter search. Features use Q or strictly earlier '
        'observations. Practice must end before Q. Train earlier seasons, score 2024, 2025 and 2026 independently. '
        'Imputation and scaling fit training rows only. Races have equal weight in reported scores. '
        'Intervals resample whole races, not laps or individual drivers. Multiple hypotheses were inspected: '
        'intervals are descriptive, not multiplicity-adjusted discovery certificates. All results are historical '
        'diagnostics, including reused 2026 outcomes; there are zero fresh prospective validation races. '
        'Linear-model failures do not prove a factor cannot help another properly tested model. '
        'Recorded lap/telemetry timestamps do not attest original publication or exclude later feed revisions.')
    limits=('Full raw position streams were verified for integrity but not fitted or analysed as trajectories. '
        'Car telemetry was summarised over sessions; throttle/brake fractions reflect driver programmes and '
        'cannot be interpreted as driving skill or causal effects. Fuels, true tyre wear, unseen damage, '
        'setups and race-window forecast histories are not identified by this dataset. '
        'Missing or invalid Q classifications exclude some races from model fitting. DNS/DQ rows are excluded '
        'from these model targets; race scores therefore describe eligible matched driver rows rather than '
        'guaranteed full-field production forecasts. Actual race rain and neutralisations are explanatory labels only.')
    sections=[('Inventory and modelling coverage',counts),('Incremental factor scores',comparison),
              ('Scores by later season',years),('Direct earlier-results retirement priors',beta_summary),
              ('Why the qualifying baseline misses',outcome),('Actual race weather — diagnostic only',weather),
              ('Table coverage — includes outcome and diagnostic columns',coverage),('Within-race correlations — not incremental proof',correlations)]
    followup_note=''
    if followup is not None:
        followup=Path(followup)
        sections.extend([('Exploratory attribution: individual form and pace inputs',pd.read_csv(followup/'factor_family_scores.csv')),
                         ('Earlier-stage checks: fixed retrospective roster',pd.read_csv(followup/'stage_summary.csv')),
                         ('Earlier-stage scores by season',pd.read_csv(followup/'stage_year_scores.csv'))])
        followup_note=('<p>Earlier-stage checks use no target qualifying features. They rank a fixed eligible historical '
                       'roster, with driver-identity tie breaks. Their comparator is recent-driver-form order, '
                       'not the production simulation. They do not reconstruct PRE entry-list availability. '
                       'These are ranked-order errors; the main Q tables score continuous finish estimates. '
                       'The attribution follow-up was chosen after viewing the first diagnostic pass.</p>')
    body=f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Historical predictive factors</title>
<style>body{{font:15px/1.6 system-ui;color:#172337;background:#f5f7fa;max-width:1250px;margin:36px auto;padding:0 22px}}h1,h2{{color:#123e52}}section{{overflow:auto;background:white;padding:16px;border-radius:8px;margin:20px 0}}table{{border-collapse:collapse;font-size:12px;white-space:nowrap}}th,td{{padding:7px 10px;border-bottom:1px solid #dde3ea;text-align:right}}img{{max-width:100%;background:white}}summary{{cursor:pointer;font-weight:600}}a{{color:#126a77}}</style>
<h1>Historical predictive-factor analysis</h1><p>{facts['archive_sessions']:,} sessions · {facts['lap_rows']:,} laps · {facts['car_samples']:,} car samples · {facts['model_races']} eligible modelling races</p>
<p><strong>Exploratory diagnostics. No production model changed or promoted.</strong></p>
<h2>Recent form versus qualifying order</h2><p>The recent-form family scores
{comparison.set_index('variant').loc['recent_form','mae']:.3f} positions of error, compared with
{comparison.set_index('variant').loc['recent_form','q_mae']:.3f} for qualifying order. Its 95% race-bootstrap interval
for the change is [{comparison.set_index('variant').loc['recent_form','q_ci_low']:+.3f},
{comparison.set_index('variant').loc['recent_form','q_ci_high']:+.3f}]. Use the interval and the separate season
scores when deciding whether the apparent gain is reliable. The comparisons below also test whether
whole-session telemetry, timing and practice add value beyond a learned grid adjustment.</p>
<p>Matched FP2 pace covers {100*features.get('fp2_pace',pd.Series(index=features.index,dtype=float)).notna().mean():.1f}%
of modelling rows. Correlation with finishing order does not establish extra value beyond qualifying.
{100*facts['unspecified_share_of_retirements']:.1f}% of labelled retirements have unspecified causes;
the direct-prior table tests broad risk without pretending to know the mechanism.</p>
<h2>Does each factor beat qualifying order?</h2><img src="factor_effects.png" alt="Finish-error comparisons and race-bootstrap intervals">
<h2>Does the effect survive different seasons?</h2><img src="season_stability.png" alt="Year-by-year error changes">
<h2>Method</h2><p>{html.escape(methods)}</p>{followup_note}<h2>Limits</h2><p>{html.escape(limits)}</p>
<p>Interpretation guidance: <a href="https://scikit-learn.org/stable/common_pitfalls.html">scikit-learn on leakage</a>;
<a href="https://scikit-learn.org/stable/modules/permutation_importance.html">correlated-feature importance limitations</a>.
Within-race correlations and fitted coefficients are associations, not causal effects. Residuals containing Q rank
are mechanically related to that rank and require controlled comparisons.</p>'''
    for title,table in sections:
        body+=f'<details open><summary>{html.escape(title)}</summary><section>{table.to_html(index=False,border=0,float_format=lambda x:f"{x:.5f}")}</section></details>'
    body+='<p>Machine-readable evidence: <a href="report.json">report</a> · <a href="features.csv">features</a> · <a href="predictions.csv">predictions</a> · <a href="session_inventory.csv">session inventory</a></p></html>'
    (folder/'analysis_report.html').write_text(body,encoding='utf-8')
    print(json.dumps(facts,indent=2))
    print(comparison.round(5).to_string(index=False))
    print(beta_summary.round(5).to_string(index=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path)
    parser.add_argument('--followup',type=Path)
    args=parser.parse_args();render(args.folder,args.followup)
