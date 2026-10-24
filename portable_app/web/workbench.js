// Presentation for the mockup-based dashboard; all data comes from the Python API.
const pages = {
  drivers: ['Drivers', 'Season form and team-mate head-to-heads from the local race archive.'],
  accuracy: ['Accuracy', 'How frozen forecasts scored against the official results.'],
  scenario: ['What if', 'Change one thing, run it against Race setup, and compare.'],
  nextforecast: ['Freeze a forecast', 'Run and freeze the forecast for the next race so it can be scored afterwards.'],
  hub: ['Race weekend', 'The forecast, the schedule and the title fight for the selected Grand Prix.'],
  setup: ['Race setup', 'Configure your race simulation parameters and output preferences.'],
  data: ['Data sources', 'Manage connected data files, configuration paths and data health.'],
  historical: ['Historical data', 'Build your own season-by-season archive of race data.'],
  training: ['Model training', 'Train and evaluate candidate models from your downloaded session archive.'],
  signals: ['Model signals', 'Inspect how the model blends baseline knowledge with session data.'],
  weather: ['Weather & risk', 'Conditions, red flags, safety cars and retirement risk for the saved run.'],
  reliability: ['Reliability', 'Inspect historical mechanical failures and simulated retirement risk.'],
  strategy: ['Tyre strategy', 'Inspect tyre recommendations, candidate scores and inventory assumptions.'],
  fantasy: ['Fantasy', 'Weekly market prices, actual Fantasy scores and separate simulation projections.'],
  dashboard: ['Results', 'Post-simulation results, insights and strategy recommendations.'],
  replay: ['Session replay', 'Replay a downloaded session and compare lap telemetry.'],
  championship: ['Championship', 'Title odds from the current standings, simulating every remaining race and sprint.'],
  compare: ['Compare runs', 'Compare probabilities and expected finishes on matched driver coverage.'],
  settings: ['Settings', 'Local workspace preferences, data paths and integration status.'],
  practice: ['Practice analysis', 'Clean sectors, lap summaries and long-run pace.'],
  quali: ['Qualifying analysis', 'One-lap pace and sector performance from saved sessions.'],
  review: ['Race review', 'Completed race observations and diagnostic outliers.'],
  track: ['Track map', 'Real saved-session telemetry and sector leaders.'],
};
const iconPaths = {
  calendar:'M4 5h16v16H4z M4 10h16 M8 3v4 M16 3v4 M8 14h2 M14 14h2 M8 18h2',
  track:'M3 17c2-5 5 1 7-3s-4-3-1-7 7-3 8 0-3 7 0 8 5-6 3-9 M3 17v3h5',
  flag:'M6 22V3 M6 4c4-3 8 3 12 0v9c-4 3-8-3-12 0 M10 4v8 M14 5v8 M18 8H6',
  network:'M12 3l8 6-3 10H7L4 9z M12 3v9 M4 9l8 3 8-3 M7 19l5-7 5 7',
  sun:'M8 18a4 4 0 1 1 1-8 5 5 0 0 1 8 4 3 3 0 0 1 0 6H8 M15 3v2 M21 7l-2 1 M9 4l1 2 M18 5a4 4 0 0 1 3 6',
  sliders:'M5 3v18 M12 3v18 M19 3v18 M2 8h6 M9 15h6 M16 6h6',
  gauge:'M4 19a10 10 0 1 1 16 0 M12 12l5-5 M5 6l2 2 M12 2v3 M20 6l-2 2 M2 13h3 M19 13h3 M8 20h8',
  wheel:'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0 M4 9h16 M5 13h5l2 7 2-7h5 M10 11h4v3h-4z',
  shirt:'M8 3l-5 4 3 5 2-2v11h8V10l2 2 3-5-5-4 M8 3c0 4 8 4 8 0',
  table:'M5 3h14v18H5z M8 7h8 M8 11h2 M13 11h3 M8 15h2 M13 15h3 M8 18h8',
  gear:'M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  folder:'M3 6h7l2 3h9v12H3z',
  cube:'M12 2l10 6v9l-10 5L2 17V8z M2 8l10 5 10-5 M12 13v9 M7 5l10 5v9',
  hash:'M9 2L7 22 M17 2l-2 20 M3 8h19 M2 16h19',
  trophy:'M8 3h8v9c0 5-8 5-8 0z M8 6H3v4c0 3 5 3 5 3 M16 6h5v4c0 3-5 3-5 3 M12 16v5 M7 22h10',
  trend:'M3 19l6-6 4 3 8-12 M16 4h5v5',
  file:'M6 2h8l5 5v15H6z M14 2v6h5 M9 13h7 M9 17h7',
  image:'M3 3h18v18H3z M3 18l7-7 4 4 3-3 4 4 M9 7h1',
  chat:'M5 4h14l3 12-4 4-3-3H9l-3 3-4-4z M8 11h1 M15 11h1',
  play:'M5 3l16 9-16 9z',
  check:'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0 M7 12l4 4 6-8',
  clock:'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0 M12 5v7l5 3',
  info:'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0 M12 11v7 M12 7v1',
  car:'M3 14l3-6h12l3 6v5h-3v-2H6v2H3z M4 13h16 M7 8l1-4h8l1 4 M6 15h2 M16 15h2',
};
function icon(name) { return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${iconPaths[name] || iconPaths.info}"></path></svg>`; }
function renderIcons() { document.querySelectorAll('[data-icon]').forEach(el => el.innerHTML = icon(el.dataset.icon)); }
function navigate(view) {
  if (!$(`view-${view}`)) return;
  state.view = view;
  document.querySelectorAll('.nav-item').forEach(el => { el.classList.toggle('active', el.dataset.view === view); if (el.dataset.view) el.setAttribute('aria-current', el.dataset.view === view ? 'page' : 'false'); });
  document.querySelectorAll('.view').forEach(el => el.classList.toggle('active', el.id === `view-${view}`));
  $('viewTitle').textContent = pages[view]?.[0] || view;
  $('viewSubtitle').textContent = pages[view]?.[1] || '';
  document.querySelector('.main').scrollTop = 0;
  updateContext();
  document.querySelector('.context-strip').hidden = ['historical','training','replay','championship','drivers','accuracy','nextforecast'].includes(view);
  // PC following only changes what Setup and Results show; Settings has the full controls.
  document.querySelector('.automation-strip').hidden = !['setup','dashboard'].includes(view);
  if (typeof pauseReplay === 'function' && view !== 'replay') pauseReplay();
  if (view === 'replay') safeAction(refreshReplaySessions);
  clearTimeout(trainingState.timer);
  clearTimeout(fantasyArchive.timer);
  if(view==='fantasy'){safeAction(()=>refreshFantasyArchive());safeAction(pickFantasyTeam);}
  if(view==='championship')safeAction(()=>refreshChampionship());
  if(view==='hub')safeAction(refreshHub);
  if(view==='drivers')safeAction(refreshDrivers);
  if(view==='accuracy')safeAction(refreshAccuracy);
  if(view==='scenario')renderScenarioControls();
  if(view==='nextforecast')safeAction(refreshNextForecast);
  if(view==='training')safeAction(refreshModelTraining);
  if (typeof refreshHistoricalLibrary === 'function') {
    clearTimeout(state.archiveTimer);
    if (view === 'historical') safeAction(refreshHistoricalLibrary);
  }
  if (view === 'compare') safeAction(loadComparisonHistory);
  if (view === 'track') renderTrack(displayedTrack());
  if (typeof syncShell === 'function') syncShell(view);
}
// Job headings: neutral when idle, amber while working, red only for problems.
function setJobStatus(id, status) {
  const text=String(status || 'none').replaceAll('_',' ');
  $(id).textContent=text.charAt(0).toUpperCase()+text.slice(1);
  $(id).dataset.state=['failed','partial','interrupted','cancelled','paused','no_data'].includes(status)?'problem':['running','starting','cancelling'].includes(status)?'busy':status==='completed'?'done':'idle';
}
function notify(message, error=false) {
  const target = $(error ? 'appError' : 'appNotice'); target.textContent = message; target.hidden = false;
  if (!error) $('appError').hidden = true;
}
async function safeAction(action) {
  $('appError').hidden = true;
  try { return await action(); } catch (error) { notify(error.message || String(error), true); return null; }
}
function numeric(value) { return value == null || value === '' || !Number.isFinite(Number(value)) ? null : Number(value); }
function fmt(value, digits=2) { const n=numeric(value); return n == null ? 'Unknown' : n.toFixed(digits); }
function pct(value, digits=1) { const n=numeric(value); return n == null ? 'Unknown' : `${(n*100).toFixed(digits)}%`; }
function plural(count, noun) { return `${count} ${noun}${count === 1 ? '' : 's'}`; }
function formatCell(column, value) {
  if (column === 'exists') return value === true || value === 1 || value === '1' || value === 'True' ? 'Saved' : 'Not saved';
  if (value == null || value === '') return '—';
  if (column === 'size_bytes') { const bytes=numeric(value); return bytes == null ? value : bytes ? `${(bytes/1024).toFixed(1)} KB` : '—'; }
  const n=numeric(value);
  // Internal codes such as qualifying_classification read as plain words.
  if (n == null) return /^[a-z][a-z0-9]*(_[a-z0-9]+)+$/.test(value) ? value.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase()) : value;
  // Rare but possible outcomes read as "<0.1%" rather than a misleading 0.0%.
  if (/chance$/.test(column) && n > 0 && n < 0.0005) return '<0.1%';
  if (/chance$/.test(column) && n < 1 && n > 0.9995) return '>99.9%';
  if (/chance$|_dnf_rate$/.test(column)) return pct(n);
  if (/^P\d+$/.test(column)) return pct(n);
  if (/price/i.test(column)) return `$${n.toFixed(1)}m`;
  if (/_delta_pp$/.test(column)) return `${n > 0 ? '+' : ''}${n.toFixed(1)} pp`;
  if (/_delta$/.test(column)) return `${n > 0 ? '+' : ''}${n.toFixed(2)}`;
  // Fixed decimals per kind of value, so a column never mixes 22.274 with 13.3.
  if (/reliability_score$/.test(column)) return (n*100).toFixed(1);
  if (/points|fantasy|ceiling|floor|positions_gained/.test(column)) return n.toFixed(1);
  if (/^(avg_finish|avg_grid|finish_p\d+|expected_position)$/.test(column)) return n.toFixed(2);
  if (/confidence|quality|weight$/.test(column)) return n.toFixed(2);
  return Number.isInteger(n) ? String(n) : n.toFixed(3);
}
function definitions(target, pairs) {
  $(target).innerHTML = pairs.map(([label,value])=>`<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value ?? 'Unknown')}</dd></div>`).join('');
}
function overviewMetric(name) { return numeric((state.outputs.signals?.overview?.rows || []).find(row=>row.Metric === name)?.Value); }
function meanScore(column) {
  const values=(state.outputs.signals?.drivers?.rows || []).map(row=>numeric(row[column])).filter(v=>v!=null);
  return values.length ? values.reduce((a,b)=>a+b,0)/values.length : null;
}
function compact(payload, columns, limit=22) { return {columns: columns.filter(key=>(payload?.columns || []).includes(key)), rows: (payload?.rows || []).slice(0,limit)}; }
function updateWorkbenchContext() {
  $('sidebarSeason').textContent = `${readSettings().year} Season · local data`;
  $('modelVersion').textContent = state.reference?.version === 'phase_1_performance_profile' ? 'Performance v1' : state.reference?.version || 'Not recorded';
  $('modelVersion').title = state.reference?.version || '';
  const isSetup=['setup','data','settings'].includes(state.view);
  $('weatherSource').textContent = isSetup ? (state.setupWeather ? 'Open-Meteo ensemble' : 'Not captured') :
    state.outputs.weather?.source === 'fastf1_session_weather' ? 'Session observations' : state.outputs.details?.raceWeather?.scenarios?.length ? 'Open-Meteo ensemble' : 'Not recorded';
  const profile=state.setupOptions?.trackProfile || {};
  definitions('venueOverview', [['Circuit', profile.circuit_name || 'Unresolved'], ['Venue country', profile.venue_country],
    ['Race distance', profile.race_laps ? `${profile.race_laps} laps` : 'Generic assumption'],
    ['Circuit identity', profile.venue_status || 'Unknown'], ['Track factors', (profile.profile_status || 'unknown').replaceAll('_',' ')]]);
  const bad=(state.outputs.dataHealth || []).filter(row=>row.status !== 'valid');
  const values=readSettings();
  const valid=values.n_sims>=1 && values.n_sims<=100000 && values.n_baseline_races>=0 && values.n_baseline_races<=24 && values.historical_strategy_lookback_years>=0 && values.historical_strategy_lookback_years<=20;
  if (!$('runButton').disabled) $('runState').textContent = !valid ? 'Review parameters' : bad.length ? 'Review data warnings' : 'Ready to run';
  $('readinessMessage').textContent = !valid ? 'Some values are outside supported bounds.' : bad.length ? `${bad.length} source warnings; review Data Sources.` : values.session==='R' ? 'Race data produces a retrospective simulation.' : 'Parameters are set. Input downloads may require internet.';
  const elapsed=state.outputs.details?.run?.elapsed_seconds;
  $('lastRuntime').textContent = elapsed == null ? 'Not recorded' : `${Number(elapsed).toFixed(1)} s`;
  drawSetupTrack(profile);
}
function drawSetupTrack(profile) {
  const track=setupDisplayTrack(), points=track?.points || [];
  $('setupTrackSource').textContent=track?.message || 'Select a race to inspect downloaded telemetry.';
  $('setupTrackMap').innerHTML=points.length ? trackSvg(points,`${profile.circuit_name || 'Circuit'} outline`) :
    trackMessage(track?.status==='loading'?'Loading downloaded telemetry…':'No downloaded track outline','Select detailed sessions with position telemetry');
}
function setupDisplayTrack() {
  const selected=readSettings(), event=state.setupOptions?.trackProfile?.event;
  if(selected.event!=='latest' && selected.event!==event)return null;
  const track=state.setupTrack;
  if(track?.year===selected.year && track?.event===event && track?.points?.length)return track;
  if(track?.status==='loading')return track;
  const saved=state.outputs.savedContext || {};
  if(saved.year===selected.year && saved.event===event && state.outputs.track?.points?.length)return state.outputs.track;
  return track?.year===selected.year && track?.event===event?track:null;
}
function displayedTrack(){return state.trackViewSource==='setup'?setupDisplayTrack():state.outputs.track;}
async function refreshSetupTrack() {
  const selected=readSettings(), request=state.setupTrackRequest=(state.setupTrackRequest || 0)+1;
  const key=`${selected.year}|${selected.event}|${selected.session}`;
  state.setupTrack={year:selected.year,event:state.setupOptions?.trackProfile?.event,status:'loading',points:[],message:'Loading geometry from the downloaded historical library…'};
  drawSetupTrack(state.setupOptions?.trackProfile || {});
  try {
    const track=await api().setup_track(selected.year,selected.event,selected.session);
    const current=readSettings();
    if(request!==state.setupTrackRequest || key!==`${current.year}|${current.event}|${current.session}`)return;
    state.setupTrack=track;
  } catch(error) {
    if(request!==state.setupTrackRequest)return;
    state.setupTrack={...state.setupTrack,status:'load_failed',message:error.message || 'Downloaded telemetry could not be read.'};
  }
  drawSetupTrack(state.setupOptions?.trackProfile || {});
  if(state.view==='track' && state.trackViewSource==='setup')renderTrack(displayedTrack());
}
function renderSignals() {
  const current=overviewMetric('Avg current-session weight');
  $('blendChart').innerHTML=current == null ? '<div class="empty">No saved model weights.</div>' :
    `<div class="blend-bars"><span style="width:${Math.max(0,1-current)*100}%">${pct(1-current,0)}</span><span style="width:${Math.max(0,current)*100}%">${pct(current,0)}</span></div><div class="legend"><span>■ Baseline</span><span class="red">■ Current session</span></div>`;
  const session=state.outputs.savedContext?.session || readSettings().session;
  const weights=state.reference?.signal_weights?.[session] || {};
  $('sessionWeights').innerHTML=Object.entries(weights).map(([key,value])=>`<div class="weight-row"><span>${escapeHtml(key)} signal</span><div class="weight-track"><span style="width:${value*100}%"></span></div><b>${pct(value,0)}</b></div>`).join('');
  const metrics=[['CURRENT SIGNAL QUALITY',overviewMetric('Avg current signal quality'),'Heuristic quality; higher is cleaner data.'],
    ['MODEL UNCERTAINTY',overviewMetric('Avg model uncertainty'),'Spread score; not an error probability.'],
    ['PERFORMANCE UNCERTAINTY',overviewMetric('Avg performance uncertainty'),'Spread in projected performance.']];
  $('signalMetrics').innerHTML=metrics.map(([title,value,note])=>`<div class="signal-metric"><h3>${title}</h3><strong>${fmt(value,3)}</strong><small>${note}</small></div>`).join('');
  renderBarChart('signalScoreChart',[['Quali pace','quali_pace_score'],['Race pace','race_pace_score'],['Strategy','strategy_score'],['Reliability','reliability_score']].map(([label,column])=>({label,value:meanScore(column)})).filter(p=>p.value!=null),colors.red);
}
function renderProbabilityChart() {
  const rows=(state.outputs.summaryTable?.rows || []).slice().sort((a,b)=>Number(b.win_chance)-Number(a.win_chance)).slice(0,Number($('resultTop').value));
  const maxima=Math.max(...rows.flatMap(row=>[Number(row.win_chance)||0,Number(row.podium_chance)||0]),.01);
  $('probabilityChart').innerHTML=rows.length?rows.map(row=>`<div class="probability-row"><b>${escapeHtml(row.Driver)}</b><div class="probability-bars">${['win_chance','podium_chance'].map(key=>`<div class="probability-bar ${key==='podium_chance'?'podium':''}"><span style="width:${Math.max(0,(Number(row[key])||0)/maxima*80)}%"></span><small>${pct(row[key])}</small></div>`).join('')}</div></div>`).join(''):'<div class="empty">Run a simulation to see outcome probabilities.</div>';
}
// One bar per driver: P25 to P75 of simulated finishes, with the average marked.
function renderFinishRange() {
  const ranges=(state.outputs.finishRanges || []).slice(0,Number($('resultTop').value));
  if(!ranges.length){$('finishRange').innerHTML='<div class="empty">Finish ranges were not saved for this run.</div>';return;}
  const last=Math.max(20,...(state.outputs.finishRanges || []).map(r=>Math.ceil(r.p75)));
  const x=position=>((Math.min(Math.max(position,1),last)-1)/(last-1))*100;
  $('finishRange').innerHTML=ranges.map(r=>`<div class="range-row" title="${escapeHtml(r.driver)}: P${r.p25.toFixed(0)}–P${r.p75.toFixed(0)}, average ${r.mean.toFixed(1)}"><b>${escapeHtml(r.driver)}</b><div class="range-track"><span style="left:${x(r.p25)}%;width:${Math.max(1.5,x(r.p75)-x(r.p25))}%"></span><i style="left:${x(r.mean)}%"></i></div><small>P${r.p25.toFixed(0)}–P${r.p75.toFixed(0)}</small></div>`).join('')
    +`<div class="range-axis" aria-hidden="true"><span></span><div><span>P1</span><span>P${Math.round((last+1)/2)}</span><span>P${last}</span></div><span></span></div>`;
}
function renderHeatmap() {
  const matrix=state.outputs.details?.positionMatrix || {}, fields=(matrix.columns || []).filter(key=>/^P\d+$/.test(key)).slice(0,10);
  const drivers=(state.outputs.summaryTable?.rows || []).slice(0,10).map(row=>row.Driver);
  const rows=(matrix.rows || []).filter(row=>drivers.includes(row.Driver)).sort((a,b)=>drivers.indexOf(a.Driver)-drivers.indexOf(b.Driver));
  $('finishHeatmap').innerHTML=rows.length?`<table><thead><tr><th>Driver</th>${fields.map(key=>`<th>${key.slice(1)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr><td>${escapeHtml(row.Driver)}</td>${fields.map(key=>{const value=numeric(row[key]);return `<td style="background:rgba(229,14,24,${value==null?0:Math.min(.95,.08+value*2)})" title="${key}: ${pct(value)}">${value==null?'—':pct(value,0)}</td>`;}).join('')}</tr>`).join('')}</tbody></table>`:'<div class="empty">Finish distribution has not been saved.</div>';
}
function renderResultsDetails() {
  renderProbabilityChart();renderFinishRange();renderHeatmap();
  const strategyColumn=state.outputs.strategy?.columns?.includes('primary_strategy')?'primary_strategy':'PredictedStrategy';
  renderTable('resultStrategy',compact(state.outputs.strategy,['Driver',strategyColumn,'expected_stops','strategy_confidence','risk_level'],10));
  renderTable('fantasyTable',state.outputs.details?.fantasyTable);
  renderTable('resultFantasyTable',compact(state.outputs.details?.fantasyTable,['Driver','avg_fantasy_points','fantasy_ceiling_p90','fantasy_floor_p10','fantasy_xppm'],10));
  const details=state.outputs.details || {}, run=details.run || {}, saved=state.outputs.savedContext || {};
  $('resultSims').textContent=run.settings?.n_sims ? Number(run.settings.n_sims).toLocaleString() : details.forecastRun?.n_sims ? Number(details.forecastRun.n_sims).toLocaleString() : 'Not recorded';
  $('resultRuntime').textContent=run.elapsed_seconds == null ? 'Not recorded' : `${Number(run.elapsed_seconds).toFixed(1)} s`;
  const sc=safetyCarSummary(details.risk || {});
  renderCandidateBadges(details.candidates);
  $('safetyCarMetric').hidden=numeric(details.risk?.safety_car_chance)==null;
  $('resultSafetyCar').textContent=sc.value;$('resultSafetyCarNote').textContent=sc.note;
  $('savedResultLabel').textContent=(state.outputs.summaryTable?.rows || []).length ? `${saved.year || ''} ${displayEventName(saved.event) || 'Saved run'} · ${saved.session || ''}` : 'No saved run';
  const rows=(state.outputs.summaryTable?.rows || []).slice().sort((a,b)=>Number(b.win_chance)-Number(a.win_chance));
  const notes=[];
  if (rows[0]) notes.push(`${rows[0].Driver} leads the modelled win probabilities at ${pct(rows[0].win_chance)}.`);
  if (details.venue?.circuit_name) notes.push(`This run used ${details.venue.circuit_name}, ${details.venue.race_laps || 'unknown'} laps.`);
  if (details.venue?.profile_status === 'generic_uncalibrated') notes.push('Circuit-specific calibration is unavailable; this run used generic track factors.');
  notes.push('Strategy candidate scores are heuristic. They do not isolate the effect of a tyre strategy on winning.');
  $('resultInsights').innerHTML=notes.map(note=>`<p>${escapeHtml(note)}</p>`).join('');
  const rules=state.reference?.fantasy_scoring || {};
  const team=rules.constructor?.qualifying_teamwork || {};
  definitions('fantasyRules',[['Race finish P1 to P10','25 to 1'],['Qualifying P1 to P10','10 to 1'],['Sprint finish P1 to P8','8 to 1'],
    ['Position gained / lost','±1 per place, no cap'],['Overtake',`+${rules.overtake_points ?? 1} each`],['Fastest lap (race / sprint)',`+${rules.fastest_lap_bonus} / +${rules.sprint_fastest_lap_bonus}`],
    ['Driver of the Day',`+${rules.dotd_bonus}`],['Not classified (race / sprint / qualifying)',`${rules.dnf_penalty} / ${rules.sprint_dnf_penalty} / ${rules.quali_not_classified_penalty}`],
    ['Constructor qualifying bonus',`${team.neither_q2} to +${team.both_q3}`],['Constructor fastest pit stop','+2 to +20 by time, +5 for the fastest']]);
  renderForecastViews();
}
// Model candidates: off by default, never persisted, validated again by the backend.
function renderCandidateOptions(list) {
  state.candidateOptions=list || [];
  $('candidatesPanel').hidden=!state.candidateOptions.length;
  $('candidateFields').innerHTML=state.candidateOptions.map(item=>`<label id="candidateRow-${item.key}"><span>${escapeHtml(item.label)}</span><select id="candidate-${item.key}" data-candidate="${item.key}">${item.options.map(option=>`<option value="${escapeHtml(option.value)}"${option.value===item.default?' selected':''}>${escapeHtml(option.label)}${option.lane==='correctness'?' (fact fix)':''}</option>`).join('')}</select>${item.note?`<small>${escapeHtml(item.note)}</small>`:''}</label>`).join('');
  document.querySelectorAll('[data-candidate]').forEach(el=>el.addEventListener('change',updateCandidateRules));
  updateCandidateRules();
}
function resetCandidates() {
  $('candidatesToggle').checked=false;
  state.candidateOptions?.forEach(item=>{const el=$(`candidate-${item.key}`);if(el)el.value=item.default;});
  updateCandidateRules();
}
// Mirrors the run_config rules, so impossible combinations cannot be picked.
function updateCandidateRules() {
  const on=$('candidatesToggle').checked, value=key=>$(`candidate-${key}`)?.value;
  $('candidateFields').hidden=!on;
  $('candidatePairRow').hidden=!on;
  const agent=value('race_engine')==='agent_laps_v1';
  const blocked={pair_pass_model:!agent, safety_car_model:agent, shared_noise_model:agent, grid_sampling_model:agent};
  if(!$('forecastInput').checked)blocked.weather_model=true;
  (state.candidateOptions || []).forEach(item=>{
    const el=$(`candidate-${item.key}`);if(!el)return;
    el.disabled=Boolean(blocked[item.key]);
    if(el.disabled)el.value=item.default;
    $(`candidateRow-${item.key}`).classList.toggle('unavailable',el.disabled);
  });
  const active=Object.keys(readCandidates()).length;
  $('candidateMessage').textContent=!on?'':active?`${plural(active,'candidate')} on for the next run. Results will be labelled as a candidate run.`:'All choices match the established model.';
}
function readCandidates() {
  if(!$('candidatesToggle')?.checked)return {};
  const active={};
  (state.candidateOptions || []).forEach(item=>{const el=$(`candidate-${item.key}`);if(el && !el.disabled && el.value!==item.default)active[item.key]=el.value;});
  return active;
}
function renderCandidateBadges(labels) {
  $('candidateBadges').innerHTML=(labels || []).map(label=>`<span class="candidate-badge" title="Unpromoted model candidate">${escapeHtml(label)}</span>`).join('');
}
// Safety-car numbers exist only when a run used a safety-car candidate.
function safetyCarSummary(risk) {
  if (numeric(risk.safety_car_chance)==null) return {value:'Off for this run',note:'Turn on a safety-car model under Model candidates in Race setup.'};
  const vsc=numeric(risk.vsc_chance), count=numeric(risk.avg_safety_cars);
  const parts=[count==null?null:`${count.toFixed(2)} SCs per race`,vsc==null?null:`VSC in ${pct(vsc,0)} of races`].filter(Boolean);
  return {value:pct(risk.safety_car_chance,0),note:parts.length?parts.join(' · '):'Simulated races with at least one safety car.'};
}
function renderWeatherPanels() {
  const weather=state.outputs.weather || {}, modifiers=weather.modifiers || {}, observed=weather.observed || {};
  const descriptions={chaos_factor:'Disruption multiplier',strategy_factor:'Strategy variance multiplier',dnf_factor:'Retirement risk multiplier',degradation_factor:'Tyre degradation multiplier',uncertainty_factor:'Forecast spread multiplier'};
  // A row of "Unknown" tiles says nothing; one line explains the gap instead.
  const savedModifiers=Object.keys(descriptions).some(key=>numeric(modifiers[key])!=null);
  $('modifierCards').innerHTML=!savedModifiers?'<div class="empty">Weather multipliers were not saved for this run. Turn on the session weather and race-control options in Race setup to record them.</div>':Object.entries(descriptions).map(([key,description])=>`<div class="modifier-card"><h3>${key.replace('_factor','').toUpperCase()}</h3><strong>${numeric(modifiers[key])==null?'Unknown':fmt(modifiers[key])+'×'}</strong><small>${description}<br>Read-only model output</small></div>`).join('');
  const observedAny=['air_temp_avg','track_temp_avg','rainfall_flag'].some(key=>observed[key]!=null);
  if(!observedAny)$('observedWeather').innerHTML=`<div class="empty">No session weather was saved for this run. ${escapeHtml(weather.source || '')}</div>`;
  else definitions('observedWeather',[['Air temperature',observed.air_temp_avg==null?'Not recorded':`${fmt(observed.air_temp_avg,1)} °C`],['Track temperature',observed.track_temp_avg==null?'Not recorded':`${fmt(observed.track_temp_avg,1)} °C`],['Rainfall',observed.rainfall_flag==null?'Unknown':observed.rainfall_flag?'Observed':'Not observed'],['Source',weather.source || 'Unknown']]);
  const risk=state.outputs.details?.risk || {}, sc=safetyCarSummary(risk);
  const items=[['car','Safety Car Probability',sc.value,sc.note],
    ['flag','Red Flag Probability',pct(state.outputs.details?.risk?.red_flag_chance),'Estimated from simulated event outcomes.'],
    ['gauge','Mean Driver DNF',pct(state.outputs.details?.risk?.dnf_chance),'Mean retirement chance across modelled drivers.']];
  $('riskCards').innerHTML=items.map(([symbol,title,value,note])=>`<div class="risk-item"><span>${icon(symbol)}</span><div><b>${title}</b><strong>${escapeHtml(value)}</strong><p>${note}</p></div></div>`).join('');
  renderRaceForecast();
}
function renderRaceForecast() {
  const report=state.setupWeather || state.outputs.details?.raceWeather;
  const scenarios=report?.scenarios || [], scheduled=scenarios[0], air=scheduled?.best_match?.air_temp_avg;
  const unavailable='<strong>Not captured</strong><p>Fetch a forecast for a future selected race. Historical session observations are shown separately.</p>';
  const content=scheduled ? `<strong>${air==null?'Temperature unknown':fmt(air,1)+' °C'}</strong><p>${escapeHtml(report.event || displayEventName(readSettings().event))} · race window ${escapeHtml(scheduled.start_utc || '')}<br>Captured ${escapeHtml(report.retrieved_at_utc || 'unknown')}<br>Ensemble wet-hour frequency: ${pct(scheduled.wet_hour_frequency)}</p>` : unavailable;
  $('raceForecast').innerHTML=content;$('setupWeatherPreview').innerHTML=state.setupWeather?content:unavailable;
  $('delayTable').hidden=!scenarios.length;
  renderTable('delayTable',{columns:scenarios.length?['start','wet_hour_members','complete_members','start_delay_probability']:[],rows:scenarios.map(s=>({start:s.delay_minutes?`Start +${s.delay_minutes} min`:'Scheduled',wet_hour_members:pct(s.wet_hour_frequency),complete_members:`${s.complete_member_count}/${s.member_count}`,start_delay_probability:'Unavailable'}))});
}
function renderSourceCards() {
  const data=state.outputs.dataHealth || [], symbols={fantasy_prices:'shirt',track_profiles:'track',fia_document_index:'file',team_power_units:'gear'};
  $('sourceCards').innerHTML=data.map(item=>`<button class="source-card ${item.key === (state.previewKey || 'track_profiles')?'selected':''}" data-source="${escapeHtml(item.key)}"><span class="source-title">${icon(symbols[item.key])}${escapeHtml(item.label)}</span><span class="file-name" title="${escapeHtml(item.path)}">${escapeHtml(item.path.split(/[\\/]/).pop() || 'No file configured')}</span><span class="source-stat">Rows Loaded<strong>${Number(item.row_count).toLocaleString()}</strong></span><span class="source-stat">Last Updated<strong>${escapeHtml(item.modified_at || 'Unknown')}</strong></span><span class="source-stat">Validation<strong class="${item.status==='valid'?'green':item.status==='missing'?'red':'amber'}">${escapeHtml(item.status)}</strong></span><span class="source-footer"><span>CSV rows</span><b>${Number(item.row_count).toLocaleString()}</b></span></button>`).join('');
  $('sourceCards').querySelectorAll('[data-source]').forEach(el=>el.addEventListener('click',()=>safeAction(()=>loadDataPreview(el.dataset.source,1))));
  definitions('dataHealthCounts',[['Files found',data.filter(x=>x.exists).length],['Valid CSVs',data.filter(x=>x.status==='valid').length],['Invalid CSVs',data.filter(x=>x.status==='invalid').length],['Missing files',data.filter(x=>x.status==='missing').length],['Upstream freshness','Not attested']]);
  const track=data.find(x=>x.key==='track_profiles'), path=track?.path || '';
  $('dataDirectoryDisplay').textContent=path ? path.slice(0,Math.max(path.lastIndexOf('/'),path.lastIndexOf('\\'))) : 'No directory configured';
  if (!$('dataDirectoryInput').value) $('dataDirectoryInput').value=$('dataDirectoryDisplay').textContent;
}
// One empty state per analysis view instead of a wall of "Unknown" cards.
function renderRunEmptyStates() {
  const hasRun=(state.outputs.summaryTable?.rows || []).length>0;
  document.body.classList.toggle('no-run',!hasRun);
  ['dashboard','signals','weather','reliability','strategy'].forEach(view=>{
    const section=$(`view-${view}`);if(!section)return;
    let note=section.querySelector(':scope > .run-empty');
    if(!note){
      note=document.createElement('div');note.className='run-empty';note.setAttribute('role','status');
      note.innerHTML='<div><b>No saved run yet</b><p>Run a simulation from Race setup, or turn on Follow PC runs there to load the latest automated forecast.</p></div><button type="button" class="primary">Go to Race setup</button>';
      note.querySelector('button').addEventListener('click',()=>navigate('setup'));
      section.prepend(note);
    }
    note.hidden=hasRun;
  });
}
function renderWorkbench() {
  renderSourceCards();renderSignals();renderResultsDetails();renderWeatherPanels();updateWorkbenchContext();renderRunEmptyStates();
  $('discordConfiguration').innerHTML='';
  definitions('discordConfiguration',[['Webhook',state.initial?.discordConfigured?'Configured locally':'Not configured'],['Automatic uploads','Off for manual simulations'],['Upload target','Verified frozen forecast in Simulation Centre']]);
}
async function loadDataPreview(key=state.previewKey || 'track_profiles',page=1) {
  const preview=await api().workbench_data(key,page);state.previewKey=key;state.previewPage=preview.page;state.previewPages=preview.pages;
  $('previewTitle').textContent=`Data preview: ${preview.source.label.toLowerCase()}${preview.sort?.direction==='desc'?' · newest first':''}`;
  $('previewPath').textContent=preview.source.path;
  const keys={track_profiles:['Event','CircuitName','RaceLaps','OvertakingDifficulty','SafetyCarChance','RedFlagBaseChance','ProfileStatus'],team_power_units:['Year','Team','PowerUnitSupplier','EngineBadge','OfficialTeamLabel'],fantasy_prices:['Driver','Team','fantasy_price'],fia_document_index:['published_at','year','event','session','doc_number','document_title']};
  if(key==='fia_document_index' && preview.columns.includes('published_at'))preview.columns=['published_at',...preview.columns.filter(column=>column!=='published_at')];
  state.outputs.dataHealth=(state.outputs.dataHealth || []).map(source=>source.key===key?preview.source:source);
  const columns=(keys[key] || []).filter(column=>preview.columns.includes(column));
  renderTable('dataPreviewTable',state.showAllColumns || columns.length<2?preview:{...preview,columns},{sortable:false});
  $('previewCount').textContent=preview.source.status!=='valid'?preview.source.message:`Showing ${preview.rows.length ? (preview.page-1)*10+1 : 0}–${Math.min(preview.page*10,preview.source.row_count)} of ${preview.source.row_count} rows`;
  $('previewPage').textContent=`${preview.page} / ${preview.pages}`;$('previewPrevious').disabled=preview.page<=1;$('previewNext').disabled=preview.page>=preview.pages;
  $('validationTime').textContent=new Date(preview.checked_at_utc).toLocaleString();renderSourceCards();
}
async function reloadData(announce=true,resetPreview=announce) {
  const status=await api().workbench_status();state.outputs.dataHealth=status.dataHealth;state.initial.discordConfigured=status.discordConfigured;
  renderSourceCards();renderTable('dataHealthTable',{columns:['label','status','row_count','modified_at','message','path'],rows:status.dataHealth});
  await loadDataPreview(state.previewKey,resetPreview && state.previewKey==='fia_document_index'?1:state.previewPage || 1);updateWorkbenchContext();if(announce)notify('Data sources reloaded and validated.');
}
async function fetchRaceWeather() {
  const selected=readSettings(); notify('Fetching an informational race forecast…');
  const report=await api().workbench_weather(selected.year, selected.event);
  state.setupWeather={...report,event:state.setupOptions?.trackProfile?.event || selected.event};
  renderRaceForecast();updateWorkbenchContext();notify('Race forecast captured locally. Driver probabilities are unchanged.');
}
async function loadComparisonHistory() {
  const history=(await api().workbench_history()).history || [];
  const runs=history.filter(r=>['monte_carlo','forecast'].includes(r.kind) && ['completed','existing'].includes(r.status));
  ['compareA','compareB'].forEach((id,index)=>{const selected=$(id).value;$(id).innerHTML=runs.map(r=>`<option value="${escapeHtml(r.id)}">${escapeHtml(r.label)} · ${escapeHtml(r.created_at?.slice(0,16)||'')}</option>`).join('');if(runs.some(r=>r.id===selected))$(id).value=selected;else if(runs[index])$(id).value=runs[index].id;});
  $('compareRuns').disabled=runs.length<2;
  // A baseline-plus-candidate pair opens straight into its comparison.
  const preset=state.comparePreset, find=dir=>runs.find(r=>r.outputDir===dir)?.id;
  if(preset && find(preset.baseline) && find(preset.candidate)){
    state.comparePreset=null;$('compareA').value=find(preset.baseline);$('compareB').value=find(preset.candidate);
    renderTable('comparisonTable',await api().workbench_compare($('compareA').value,$('compareB').value));
    notify('Run A is the established model and Run B the candidate, both with the same seed.');
    return;
  }
  if(runs.length<2)$('comparisonTable').innerHTML=`<div class="empty">${runs.length?'Only one saved run so far. Save a second run to compare.':'No saved runs yet. Run a simulation from Race setup first.'}</div>`;
}
function applyPreferences(preferences) {
  $('autoReloadInput').checked=Boolean(preferences.auto_reload);updateAutoReload();
  if(preferences.settings_error)notify(preferences.settings_error,true);
}
function updateAutoReload() {
  clearInterval(state.dataTimer);
  if($('autoReloadInput').checked)state.dataTimer=setInterval(()=>safeAction(()=>reloadData(false)),15000);
}
async function savePreferences(dataDirectory=false) {
  const result=await api().workbench_save(readSettings(),dataDirectory?$('dataDirectoryInput').value:'',$('autoReloadInput').checked);
  state.outputs.dataHealth=result.dataHealth;state.initial.discordConfigured=result.discordConfigured;renderSourceCards();
  updateAutoReload();notify('App settings saved locally. Discord uploads remain opt-in.');
}
async function resetForm() {
  const defaults={...(state.projectDefaults || state.initial.settings),...(state.automation?.latest?.context || {})};
  setOptions($('yearInput'),state.initial.seasons,defaults.year);
  const events=await api().events_for_year(defaults.year);setOptions($('eventInput'),events,defaults.event);
  writeSettings(defaults);resetCandidates();await refreshSetupOptions(defaults.session);renderSessionPills();notify('Setup restored to defaults for the latest PC forecast. Saved results are unchanged.');
}
function initWorkbench() {
  renderIcons();
  initFantasyArchive();initFantasyPicker();
  initChampionship();
  document.querySelectorAll('[data-open-view]').forEach(el=>el.addEventListener('click',()=>{
    if(el.dataset.openView==='track')state.trackViewSource=el.dataset.trackSource || 'saved';
    navigate(el.dataset.openView);
  }));
  document.querySelectorAll('[data-open-data]').forEach(el=>el.addEventListener('click',()=>safeAction(()=>api().workbench_open_data(el.dataset.openData))));
  document.querySelectorAll('[data-export]').forEach(el=>el.addEventListener('click',()=>safeAction(async()=>{const result=await api().workbench_export(state.outputs.outputDir || readSettings().output_dir,el.dataset.export);notify(`Exported ${result.files.length} file(s) to ${result.folder}. Nothing was uploaded.`);})));
  $('previewPrevious').addEventListener('click',()=>safeAction(()=>loadDataPreview(state.previewKey,state.previewPage-1)));
  $('previewNext').addEventListener('click',()=>safeAction(()=>loadDataPreview(state.previewKey,state.previewPage+1)));
  $('openDataEditor').addEventListener('click',()=>safeAction(()=>api().workbench_open_data(state.previewKey || 'track_profiles')));
  $('reloadData').addEventListener('click',()=>safeAction(()=>reloadData()));
  $('validationLog').addEventListener('click',()=>{const details=$('dataValidationDetails');details.open=true;details.scrollIntoView({behavior:'smooth'});});
  ['fetchSetupWeather','fetchWeather'].forEach(id=>$(id).addEventListener('click',()=>safeAction(fetchRaceWeather)));
  $('autoReloadInput').addEventListener('change',()=>safeAction(()=>savePreferences(false)));
  $('saveSettings').addEventListener('click',()=>safeAction(()=>savePreferences(true)));
  ['resetSetup','resetSettings'].forEach(id=>$(id).addEventListener('click',()=>safeAction(resetForm)));
  $('candidatesToggle').addEventListener('change',updateCandidateRules);
  $('forecastInput').addEventListener('change',updateCandidateRules);
  $('discordSetup').addEventListener('click',()=>window.location.href='centre.html');
  $('refreshComparisons').addEventListener('click',()=>safeAction(loadComparisonHistory));
  $('compareRuns').addEventListener('click',()=>safeAction(async()=>{
    if($('compareA').value===$('compareB').value){$('comparisonTable').innerHTML='<div class="empty">Run A and Run B are the same run. Pick two different runs.</div>';return;}
    renderTable('comparisonTable',await api().workbench_compare($('compareA').value,$('compareB').value));
  }));
  $('resultTop').addEventListener('change',()=>{renderProbabilityChart();renderFinishRange();});
  $('outputInput').addEventListener('change',()=>{state.activeOutputDir=null;safeAction(refreshOutputs);});
  ['baselineInput','lookbackInput','seedInput'].forEach(id=>$(id).addEventListener('change',updateContext));
  $('sessionInput').addEventListener('change',()=>safeAction(refreshSetupTrack));
  $('refreshButton').addEventListener('click',()=>safeAction(refreshSetupTrack));
  $('yearInput').addEventListener('change',()=>{state.setupWeather=null;renderRaceForecast();});
  $('eventInput').addEventListener('change',()=>{state.setupWeather=null;renderRaceForecast();});
  document.querySelectorAll('form').forEach(form=>form.addEventListener('submit',event=>event.preventDefault()));
  api().workbench_status().then(status=>$('workspacePath').textContent=status.workspace).catch(error=>notify(error.message,true));
}
window.addEventListener('pywebviewready',()=>safeAction(boot));
if(window.f1Api)safeAction(boot);
