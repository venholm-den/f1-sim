// Drivers, Accuracy and the Lab's what-if runs. Drivers and Accuracy read saved
// files through the API; a what-if runs Race setup twice and opens Compare.

const insights = {drivers:null, driversError:'', accuracy:null, accuracyError:'', selectedScore:null, request:0, scoring:null};

// ---------- Drivers ----------
function driversAnswers(data) {
  const drivers=data?.drivers || [];
  if (!drivers.length) return [];
  const leader=drivers[0];
  const winner=[...drivers].sort((a,b)=>b.wins-a.wins || b.points-a.points)[0];
  const answers=[{label:'Points leader', value:`${leader.driver} · ${Math.round(leader.points)}`, note:`${leader.team}, after ${plural(data.rounds,'round')}`},
    {label:'Most wins', value:winner.wins ? `${winner.driver} · ${winner.wins}` : '—', note:winner.wins ? `${plural(winner.podiums,'podium')} in total` : 'no Grand Prix wins yet'}];
  const close=(data.pairs || []).filter(p=>p.a_ahead+p.b_ahead>=3).sort((a,b)=>Math.abs(a.a_ahead-a.b_ahead)-Math.abs(b.a_ahead-b.b_ahead))[0];
  if (close) answers.push({label:'Closest team-mates', value:`${close.a} ${close.a_ahead}–${close.b_ahead} ${close.b}`, note:`${close.team}, races both finished`});
  const regulars=drivers.filter(d=>d.races>=Math.ceil(data.rounds/2));
  const reliable=[...regulars].sort((a,b)=>a.retirements-b.retirements || b.races-a.races)[0];
  if (reliable) answers.push({label:'Fewest retirements', value:`${reliable.driver} · ${reliable.retirements}`, note:`in ${plural(reliable.races,'race')}`});
  return answers;
}

function renderDrivers() {
  const data=insights.drivers;
  if (!data) {
    $('driversAnswers').hidden=true;
    ['driversPoints','driverPairs','driversTable'].forEach(id=>{$(id).innerHTML=`<div class="empty">${escapeHtml(insights.driversError || 'Loading the season…')}</div>`;});
    return;
  }
  $('driversAnswers').hidden=false;
  $('driversAnswers').innerHTML=answerTiles(driversAnswers(data));
  $('driversContext').textContent=`${data.year} · ${plural(data.rounds,'Grand Prix')} in the local archive. Points include sprints.`;
  renderBarChart('driversPoints',data.drivers.slice(0,12).map(d=>({label:d.driver,value:d.points,text:String(Math.round(d.points))})),colors.red);
  $('driverPairs').innerHTML=data.pairs.length ? data.pairs.map(p=>{
    const both=p.a_ahead+p.b_ahead, share=both ? p.a_ahead/both*100 : 50;
    return `<div class="pair-row"><b data-driver="${escapeHtml(p.a)}">${escapeHtml(p.a)}</b><div class="pair-bar" title="${escapeHtml(p.team)}: ${p.a_ahead}–${p.b_ahead} in ${plural(both,'race')} both finished"><span style="width:${share}%"></span><small>${p.a_ahead}</small><small>${p.b_ahead}</small></div><b data-driver="${escapeHtml(p.b)}">${escapeHtml(p.b)}</b><em>${escapeHtml(p.team)}</em></div>`;
  }).join('') : '<div class="empty">No team-mates raced together this season.</div>';
  renderTable('driversTable',{columns:['Driver','Team','races','wins','podiums','points','avg_finish','best_finish','retirements'],
    rows:data.drivers.map(d=>({Driver:d.driver,Team:d.team,races:d.races,wins:d.wins,podiums:d.podiums,points:d.points,avg_finish:d.avg_finish,best_finish:d.best_finish,retirements:d.retirements}))});
}

async function refreshDrivers() {
  const request=++insights.request, year=Number($('driversSeason').value) || null;
  insights.drivers=null; insights.driversError=''; renderDrivers();
  try { const data=await api().driver_intel(year); if (request===insights.request) insights.drivers=data; }
  catch (error) { if (request===insights.request) insights.driversError=String(error?.message || error).replace(/^Error:\s*/,''); }
  if (request===insights.request) renderDrivers();
}

// ---------- Accuracy ----------
function signedPercent(value) { return value==null ? '—' : `${value>=0?'+':'−'}${Math.abs(Math.round(value*100))}%`; }
function mean(values) { const v=values.filter(x=>x!=null && Number.isFinite(Number(x))).map(Number); return v.length ? v.reduce((a,b)=>a+b,0)/v.length : null; }

function accuracyAnswers(data) {
  const scored=data?.scored || [];
  if (!scored.length) return [];
  const mae=mean(scored.map(r=>r.finish_mae)), win=mean(scored.map(r=>r.win_chance_skill)), podium=mean(scored.map(r=>r.podium_chance_skill));
  return [{label:'Races scored', value:String(scored.length), note:`latest ${scored[0].year || ''} ${scored[0].event || ''}`.trim()},
    {label:'Finish error', value:mae==null ? '—' : `${mae.toFixed(1)} places`, note:'average gap between predicted and actual finish'},
    {label:'Win calls', value:signedPercent(win), note:'Brier skill against an even guess'},
    {label:'Podium calls', value:signedPercent(podium), note:'Brier skill against an even guess'}];
}

function renderAccuracyScatter(race) {
  const rows=(race?.comparison || []).filter(r=>r.avg_finish!=null && r.actual_position!=null);
  if (!rows.length) { $('accuracyScatter').innerHTML='<div class="empty">Choose a scored race to compare its forecast with the result.</div>'; return; }
  const n=Math.max(...rows.map(r=>Math.max(r.actual_position,Math.ceil(r.avg_finish)))), W=440, H=360, L=40, R=14, T=12, B=38;
  const px=v=>L+(v-1)/(n-1)*(W-L-R), py=v=>T+(v-1)/(n-1)*(H-T-B);
  const ticks=[1,5,10,15,20].filter(v=>v<=n);
  const grid=ticks.map(v=>`<line x1="${L}" x2="${W-R}" y1="${py(v)}" y2="${py(v)}"/><text x="${L-6}" y="${py(v)+4}" text-anchor="end">P${v}</text><text x="${px(v)}" y="${H-B+16}" text-anchor="middle">P${v}</text>`).join('');
  const dots=rows.map(r=>{const off=Math.abs(r.avg_finish-r.actual_position)>=5;
    return `<g class="scatter-point${off?' picked':''}" data-driver="${escapeHtml(r.Driver)}"><title>${escapeHtml(r.Driver)}: forecast ${Number(r.avg_finish).toFixed(1)}, finished P${r.actual_position}</title><circle cx="${px(r.avg_finish)}" cy="${py(r.actual_position)}" r="5"/>${off?`<text x="${px(r.avg_finish)+8}" y="${py(r.actual_position)+4}">${escapeHtml(r.Driver)}</text>`:''}</g>`;}).join('');
  $('accuracyScatter').innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Forecast average finish against actual finish for ${rows.length} drivers"><g class="scatter-grid">${grid}</g><line class="scatter-diagonal" x1="${px(1)}" y1="${py(1)}" x2="${px(n)}" y2="${py(n)}"/>${dots}<text class="scatter-axis" x="${(L+W-R)/2}" y="${H-4}" text-anchor="middle">Forecast average finish</text><text class="scatter-axis" transform="translate(11 ${(T+H-B)/2}) rotate(-90)" text-anchor="middle">Actual finish</text></svg>`;
  $('accuracyScatterNote').textContent=`${race.year} ${race.event}. On the line means the forecast average matched the result; red marks a miss of five places or more.`;
}

// Personal simulations stay out of the record; say how many and why in one line.
function excludedNote(excluded) {
  if (!excluded.length) return '';
  const reasons=[...new Set(excluded.flatMap(r=>r.reasons || []))];
  return `${excluded.length} personal ${excluded.length===1?'run is':'runs are'} left out of this record: ${reasons.join('; ')}.`;
}

function renderAccuracy() {
  const data=insights.accuracy;
  if (!data) { $('accuracyAnswers').hidden=true; $('accuracyTable').innerHTML=`<div class="empty">${escapeHtml(insights.accuracyError || 'Loading scored forecasts…')}</div>`; return; }
  const answers=accuracyAnswers(data);
  $('accuracyAnswers').hidden=!answers.length;
  $('accuracyAnswers').innerHTML=answerTiles(answers);
  const rows=data.scored.map(r=>({Race:`${r.year || ''} ${r.event || 'Unknown race'}`.trim(), Forecast:r.session || '—', Category:r.category || '—', Drivers:r.drivers,
    'Finish error':r.finish_mae==null?'—':`${Number(r.finish_mae).toFixed(2)} places`, 'Win skill':signedPercent(r.win_chance_skill),
    'Podium skill':signedPercent(r.podium_chance_skill), 'Top 10 skill':signedPercent(r.points_chance_skill), id:r.id}));
  $('accuracyTable').innerHTML=rows.length ? `<table><thead><tr>${['Race','Drivers','Finish error','Win skill','Podium skill','Top 10 skill'].map(c=>`<th>${c}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>
    `<tr class="selectable-row${r.id===insights.selectedScore?' focused':''}" data-score="${escapeHtml(r.id)}" tabindex="0">${['Race','Drivers','Finish error','Win skill','Podium skill','Top 10 skill'].map(c=>`<td>${escapeHtml(r[c])}</td>`).join('')}</tr>`).join('')}</tbody></table>`
    : '<div class="empty">No forecasts have been scored yet. Score a frozen forecast below once its race has finished.</div>';
  $('accuracyTable').querySelectorAll('[data-score]').forEach(el=>{
    const pick=()=>{ insights.selectedScore=el.dataset.score; renderAccuracy(); };
    el.addEventListener('click',pick); el.addEventListener('keydown',e=>{ if(e.key==='Enter')pick(); });
  });
  renderAccuracyScatter(data.scored.find(r=>r.id===insights.selectedScore) || data.scored[0]);
  const excluded=data.excluded || [];
  $('accuracyExcluded').hidden=!excluded.length;
  $('accuracyExcluded').textContent=excludedNote(excluded);
  renderPendingForecasts();
}

async function refreshAccuracy() {
  try { insights.accuracy=await api().accuracy_state(); insights.accuracyError=''; }
  catch (error) { insights.accuracy=null; insights.accuracyError=String(error?.message || error).replace(/^Error:\s*/,''); }
  renderAccuracy();
}

// ---------- Scoring and frozen forecasts (from the Simulation Centre) ----------
// Both run as background jobs; the page polls the job until it finishes, then reloads.
async function followJob(jobId, statusId, done) {
  const status=await api().lab_status(jobId);
  if (status.status==='running' || status.status==='queued') {
    $(statusId).textContent=`${status.label || 'Job'} running…${status.progress ? ` ${status.progress[0].toLocaleString('en-GB')} of ${status.progress[1].toLocaleString('en-GB')} simulations.` : ''}`;
    setTimeout(()=>safeAction(()=>followJob(jobId,statusId,done)),2000);
    return;
  }
  const reason=status.error || (status.log || '').trim().split('\n').filter(Boolean).at(-1) || '';
  $(statusId).textContent=status.status==='completed' ? 'Finished.' : `${status.status==='waiting_for_results' ? 'Results are not ready yet.' : 'Did not finish.'} ${reason}`.trim();
  await done(status);
}

function renderPendingForecasts() {
  const pending=insights.accuracy?.pending || [];
  $('accuracyPending').innerHTML=pending.length ? pending.map(f=>`<li><div><b>${escapeHtml(`${f.year || ''} ${f.event || 'Frozen forecast'}`.trim())}</b><small>${escapeHtml(f.session || '')} inputs · frozen ${f.created_at ? new Date(f.created_at).toLocaleString() : 'at an unknown time'}${f.race_start_utc ? ` · race ${new Date(f.race_start_utc).toLocaleString()}` : ''}</small></div><button type="button" class="ghost" data-score-forecast="${escapeHtml(f.id)}"${insights.scoring?' disabled':''}>Score against results</button></li>`).join('')
    : '<li class="empty">Every frozen forecast has been scored.</li>';
  $('accuracyPending').querySelectorAll('[data-score-forecast]').forEach(el=>el.addEventListener('click',()=>safeAction(()=>scoreForecast(el.dataset.scoreForecast))));
}

async function scoreForecast(forecastId) {
  insights.scoring=forecastId; renderPendingForecasts();
  $('accuracyJobStatus').textContent='Starting the score…';
  try {
    const job=await api().lab_start({kind:'score', forecast_id:forecastId});
    await followJob(job.id,'accuracyJobStatus',async()=>{ insights.scoring=null; await refreshAccuracy(); });
  } catch (error) { insights.scoring=null; renderPendingForecasts(); throw error; }
}

async function checkNextRace() {
  $('nextForecastInfo').textContent='Checking the next race…';
  const race=await api().lab_next_race();
  $('nextForecastInfo').textContent=`${race.year} ${race.event} · ${race.session} inputs · race ${new Date(race.race_start_utc).toLocaleString()}. Availability is checked again when the forecast runs.`;
}

async function freezeNextForecast() {
  const lab=await api().lab_state();
  const defaults=lab.forecast_defaults || {};
  $('nextForecastRun').disabled=true;
  $('nextForecastStatus').textContent='Starting the forecast…';
  try {
    const job=await api().lab_start({kind:'forecast', ...defaults});
    await followJob(job.id,'nextForecastStatus',async(status)=>{
      if (status.status==='completed') $('nextForecastStatus').textContent='Frozen. It is listed under Accuracy until it is scored.';
    });
  } finally { $('nextForecastRun').disabled=false; }
}

async function refreshNextForecast() {
  const lab=await api().lab_state(), d=lab.forecast_defaults || {};
  $('nextForecastProtocol').textContent=`${Number(d.n_sims || 0).toLocaleString('en-GB')} simulations · seed ${d.seed} · overtaking ${Math.round((d.overtaking_difficulty || 0)*100)}, the same protocol as automated PC forecasts so frozen snapshots stay comparable.`;
  $('nextForecastRun').disabled=Boolean(lab.active_id);
}

// ---------- Lab: what if ----------
// The changes B makes to A, in words. Nothing runs when this is empty.
function scenarioChanges(base, overrides, candidates, options) {
  const changes=[];
  if (overrides.default_overtaking_difficulty!=null && Math.abs(overrides.default_overtaking_difficulty-base.default_overtaking_difficulty)>1e-9)
    changes.push(`Overtaking difficulty ${Math.round(base.default_overtaking_difficulty*100)} → ${Math.round(overrides.default_overtaking_difficulty*100)}`);
  for (const [key,value] of Object.entries(candidates || {})) {
    const item=(options || []).find(o=>o.key===key), option=item?.options.find(o=>o.value===value);
    changes.push(`${item?.label || key}: ${option?.label || value}`);
  }
  return changes;
}

function renderScenarioControls() {
  const options=state.candidateOptions || [];
  $('scenarioModels').innerHTML=options.length ? options.map(item=>`<label><span>${escapeHtml(item.label)}</span><select data-scenario-candidate="${escapeHtml(item.key)}">${item.options.map(o=>`<option value="${escapeHtml(o.value)}"${o.value===item.default?' selected':''}>${escapeHtml(o.label)}${o.value===item.default?' (established)':''}</option>`).join('')}</select></label>`).join('')
    : '<p class="footnote">No model candidates are available in this build.</p>';
  $('scenarioModels').querySelectorAll('select').forEach(el=>el.addEventListener('change',updateScenarioSummary));
  updateScenarioSummary();
}

function readScenario() {
  const base=readSettings(), candidates={};
  document.querySelectorAll('[data-scenario-candidate]').forEach(el=>{
    const item=(state.candidateOptions || []).find(o=>o.key===el.dataset.scenarioCandidate);
    if (item && el.value!==item.default) candidates[item.key]=el.value;
  });
  return {base, overrides:{default_overtaking_difficulty:Number($('scenarioOvertaking').value)/100}, candidates};
}

function updateScenarioSummary() {
  const base=readSettings();
  if (!$('scenarioOvertaking').dataset.touched) $('scenarioOvertaking').value=Math.round(base.default_overtaking_difficulty*100);
  $('scenarioOvertakingValue').textContent=$('scenarioOvertaking').value;
  $('scenarioBase').textContent=`A: ${base.year} ${displayEventName(base.event)} · ${base.session} · ${base.n_sims.toLocaleString('en-GB')} races · seed ${base.random_seed} · overtaking ${Math.round(base.default_overtaking_difficulty*100)}`;
  const {overrides,candidates}=readScenario(), changes=scenarioChanges(base,overrides,candidates,state.candidateOptions);
  $('scenarioDiff').innerHTML=changes.length ? changes.map(c=>`<li>${escapeHtml(c)}</li>`).join('') : '<li class="empty">B matches A. Change something above to run a what-if.</li>';
  $('scenarioRun').disabled=!changes.length || Boolean(state.manualRunning);
}

async function runScenario() {
  const {base,overrides,candidates}=readScenario();
  if (!scenarioChanges(base,overrides,candidates,state.candidateOptions).length) return;
  await setPcFollowing(false);
  // A runs first with Race setup as it stands; B reuses its seed so only the chosen changes differ.
  state.pairRun={settings:{...base,...overrides}, candidates, baseline:null};
  $('scenarioState').textContent='Running A (Race setup as it stands)…';
  await launchRun(base,{});
}

function initInsights() {
  const now=new Date().getUTCFullYear();
  setOptions($('driversSeason'),[now,now-1,now-2,now-3].map(String),String(now));
  $('driversSeason').addEventListener('change',()=>safeAction(refreshDrivers));
  $('accuracyRefresh').addEventListener('click',()=>safeAction(refreshAccuracy));
  $('scenarioOvertaking').addEventListener('input',()=>{ $('scenarioOvertaking').dataset.touched='1'; updateScenarioSummary(); });
  $('scenarioReset').addEventListener('click',()=>{ delete $('scenarioOvertaking').dataset.touched; renderScenarioControls(); });
  $('scenarioRun').addEventListener('click',()=>safeAction(runScenario));
  $('nextForecastCheck').addEventListener('click',()=>safeAction(checkNextRace));
  $('nextForecastRun').addEventListener('click',()=>safeAction(freezeNextForecast));
}

if (typeof module !== 'undefined' && module.exports) module.exports = { driversAnswers, accuracyAnswers, scenarioChanges, signedPercent, excludedNote };
else initInsights();
