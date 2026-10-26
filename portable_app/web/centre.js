const el = id => document.getElementById(id);
const client = () => window.pywebview?.api || window.f1Api;
const labels = {monte_carlo:'Monte Carlo',lap_dynamics:'Lap dynamics',experiments:'Scenario experiments'};
const scenarioNames = {all:'All 11 scenarios',baseline:'Baseline',stops_0:'Zero stops (diagnostic)',stops_1:'One stop',stops_2:'Two stops',stops_3:'Three stops',pit_early_5:'Pit 5 laps earlier',pit_late_5:'Pit 5 laps later',degradation_low:'Degradation −25%',degradation_high:'Degradation +25%',pit_loss_low:'Pit loss −5 seconds',pit_loss_high:'Pit loss +5 seconds'};
let kind='monte_carlo', selected=null, appState={}, currentRows=[], lastStatus='', booted=false, loading=0;
let historicalEvents=[], historicalLoading=false, historicalRequest=0;
let reusableSource=null;
let sharingMessage='';
const escape = value => String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
// Monte Carlo inputs start from the Race Setup defaults; "Forecast next race"
// keeps the frozen PC-automation protocol and says so.
let runDefaultsApplied=false;
function forecastDefaults(){return appState?.forecast_defaults || {n_sims:100000,seed:42,overtaking_difficulty:.55};}
function applyRunDefaults(){
  const run=appState?.run_defaults, forecast=forecastDefaults();
  if(run && !runDefaultsApplied){el('nSims').value=run.n_sims;el('seed').value=run.seed;el('difficulty').value=run.overtaking_difficulty;runDefaultsApplied=true;}
  el('forecastProtocol').textContent=`${Number(forecast.n_sims).toLocaleString()} simulations · seed ${forecast.seed}, the same as automated PC forecasts so snapshots stay comparable`+(run && Number(run.n_sims)!==Number(forecast.n_sims)?` (Race Setup uses ${Number(run.n_sims).toLocaleString()})`:'')+' · neutral weather modifiers.';
}
function error(message){el('error').textContent=message;el('error').hidden=!message;}
async function safely(action){try{await action();}catch(e){error(e.message||String(e));}}
function options(id, values, allLabel, previous){
  const node=el(id);node.replaceChildren(new Option(allLabel,''));
  values.forEach(value=>node.add(new Option(scenarioNames[value]||value,value)));
  node.value=values.includes(previous)?previous:'';
}
function controls(){
  const busy=Boolean(appState.active_id);
  el('forecastNext').disabled=busy;el('scoreForecast').disabled=busy;
  el('uploadDiscord').disabled=busy||!appState.discord_configured;
  el('discordStatus').textContent=appState.discord_configured?'Discord configured locally':'Discord not configured: add a local .env.discord file';
  const historical=el('inputSource').value==='historical';
  el('savedSource').hidden=historical;el('historicalSource').hidden=!historical;
  const ready=historical?!historicalLoading&&Boolean(el('historicalEvent').value&&el('historicalSession').value):appState.features&&(kind!=='experiments'||appState.strategies);
  el('launch').disabled=busy||!ready||(kind!=='monte_carlo'&&!appState.matlab);
  el('launch').innerHTML=`Start ${labels[kind]} <span>→</span>`;
  el('cancel').disabled=!busy;
  el('monteSettings').hidden=kind!=='monte_carlo';el('experimentSettings').hidden=kind!=='experiments';el('lapSettings').hidden=kind!=='lap_dynamics';
  el('assumptions').textContent=kind==='monte_carlo'?'Uses saved features with neutral weather modifiers. For fresh event data and the complete forecast pipeline, use Race Setup.':'Exploratory dynamics with assumed fuel and tyre parameters. Scenario results verify model arithmetic; they are not calibrated race predictions.';
  if(historical)el('assumptions').textContent='Builds historical inputs first, then runs the selected simulation. The preparation uses two prior baseline races and one prior season for strategy. Monte Carlo uses neutral weather modifiers.';
}
function historicalSessions(){
  const event=historicalEvents.find(e=>e.event===el('historicalEvent').value);
  const codes=event?.sessions||[];
  const names={FP1:'Practice 1',FP2:'Practice 2',FP3:'Practice 3',Q:'Qualifying',SQ:'Sprint qualifying',S:'Sprint',R:'Race (retrospective)'};
  el('historicalSession').replaceChildren(...codes.map(code=>new Option(names[code]||code,code)));
  if(codes.includes('Q'))el('historicalSession').value='Q';controls();
}
async function loadHistorical(){
  const request=++historicalRequest;historicalLoading=true;historicalEvents=[];
  el('historicalEvent').replaceChildren(new Option('Loading calendar…',''));historicalSessions();
  el('historicalNote').textContent='Loading the historical calendar…';error('');
  try{
    const events=await client().lab_historical_events(Number(el('historicalYear').value));
    if(request!==historicalRequest)return;
    historicalEvents=events;el('historicalEvent').replaceChildren(...events.map(e=>new Option(e.event,e.event)));
    el('historicalNote').textContent=`${events.length} events available. Select a session, then start any simulation below. First-time preparation may take several minutes.`;
    historicalSessions();
  }catch(e){if(request===historicalRequest){el('historicalEvent').replaceChildren(new Option('Calendar unavailable',''));el('historicalNote').textContent='Calendar could not be loaded. Check your connection and try Load races again.';}throw e;}
  finally{if(request===historicalRequest){historicalLoading=false;controls();}}
}
// Canvas colours come from the CSS tokens shared with the Workbench.
function token(name){return getComputedStyle(document.documentElement).getPropertyValue(name).trim();}
function history(){
  el('history').innerHTML=(appState.history||[]).map(run=>`<button class="${run.id===selected?'active':''}" data-id="${escape(run.id)}"><span class="state">${escape(run.status)}</span><strong>${escape(run.label)}</strong>${run.run_class?`<em class="run-class">${run.run_class==='official'?'Official forecast':'My simulation'}</em>`:''}<small>${new Date(run.created_at).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})}${run.scenario&&run.kind==='experiments'?' · '+escape(scenarioNames[run.scenario]||run.scenario):''}</small></button>`).join('')||'<p class="muted">No saved runs yet.</p>';
  el('history').querySelectorAll('button').forEach(button=>button.onclick=()=>safely(()=>selectRun(button.dataset.id)));
}
async function refresh(){
  appState=await client().lab_state(el('sourceDir').value);
  applyRunDefaults();
  el('connection').textContent='Local workspace';el('sourceContext').textContent=appState.context.label;
  el('sourceDetail').textContent=`${appState.context.drivers} drivers · ${appState.features?'Features available':'Features missing'} · ${appState.strategies?'Strategy available':'Strategy missing'}${appState.context.modified?' · Updated '+new Date(appState.context.modified).toLocaleDateString():''}`;
  el('matlabLabel').textContent=appState.matlab?'Installed':'Not found';
  // Simulink modes cannot run without MATLAB, so their cards are disabled rather than selectable.
  document.querySelectorAll('.mode[data-kind]').forEach(button=>{if(button.dataset.kind==='monte_carlo')return;
    button.disabled=!appState.matlab;button.title=appState.matlab?'':'MATLAB/Simulink was not found on this PC.';
    button.querySelector('.mode-footer>span').textContent=appState.matlab?(button.dataset.kind==='lap_dynamics'?'Installed':'Independent verification'):'Not found';});
  if(!appState.matlab&&kind!=='monte_carlo')document.querySelector('.mode[data-kind="monte_carlo"]').click();
  controls();history();
}
async function selectRun(id){selected=id;lastStatus='';sharingMessage='';el('driverFilter').value='';el('scenarioFilter').value='';el('openFolder').disabled=false;history();await status();await results();}
async function status(){
  if(!selected)return;
  const id=selected, data=await client().lab_status(id);if(selected!==id)return;
  reusableSource=data.reusable_source;el('reuseInputs').hidden=!reusableSource;
  el('frozenActions').hidden=!data.frozen||data.status!=='completed';
  el('betaMessage').hidden=!data.score&&!data.snapshot_error&&!sharingMessage;
  if(data.snapshot_error)el('betaMessage').textContent=data.snapshot_error;
  else if(data.score)el('betaMessage').textContent=`${data.score.category} evaluation · ${data.score.drivers} drivers · Finish MAE ${data.score.finish_mae.toFixed(2)} positions · Win Brier ${data.score.win_chance_brier?.toFixed(4)} · Podium Brier ${data.score.podium_chance_brier?.toFixed(4)}. Lower is better; one race is not proof of calibration.`;
  else if(sharingMessage)el('betaMessage').textContent=sharingMessage;
  if(data.forecast_context){const f=data.forecast_context;el('nextRaceInfo').textContent=`${f.year} ${f.event} · ${f.session} inputs · cutoff ${new Date(f.data_cutoff_utc).toLocaleString()} · Race ${new Date(f.race_start_utc).toLocaleString()}`;}
  el('jobTitle').textContent=data.label||appState.history?.find(r=>r.id===id)?.label||'Saved run';
  el('jobStatus').textContent=data.status;el('reviewTitle').textContent=el('jobTitle').textContent;
  const running=['running','cancelling'].includes(data.status);
  el('statusDot').classList.toggle('running',running);
  if(running&&!data.progress)el('progress').removeAttribute('value');
  else el('progress').value=data.progress?100*data.progress[0]/data.progress[1]:['completed','existing'].includes(data.status)?100:0;
  el('progressText').textContent=running?(data.progress?`${data.progress[0]} / ${data.progress[1]} simulations complete`:data.kind==='monte_carlo'?'Running Monte Carlo simulation…':'Starting simulation. MATLAB startup may take a minute.'):(data.status==='failed'?(data.error?`Run failed: ${data.error}`:'Run failed. Open the log for the error.'):data.status==='cancelled'?'Cancelled. Partial outputs may be available.':data.status==='interrupted'?'Previous app session ended unexpectedly. Partial outputs may be available.':'Saved results available below.');
  el('log').textContent=data.log||'No log was recorded for this earlier run.';
  if(running&&data.historical&&!data.log.includes('Historical inputs ready.'))el('progressText').textContent='Preparing historical inputs. First-time downloads can take several minutes.';
  if(running&&data.kind==='forecast')el('progressText').textContent='Preparing the next-race forecast and frozen snapshot. Follow the live log.';
  if(running&&data.kind==='score')el('progressText').textContent='Loading race classification and scoring the frozen forecast…';
  if(data.status==='failed'){el('log').parentElement.open=true;}
  if(lastStatus&&lastStatus!==data.status&&!running){await refresh();await results();}
  lastStatus=data.status;
}
const headings={Driver:'Driver',Team:'Team',scenario:'Scenario',simulated_rank:'Rank',avg_finish:'Avg. finish',win_chance:'Win %',podium_chance:'Podium %',dnf_chance:'DNF %',points_chance:'Top 10 % (legacy)',top10_chance:'Top 10 %',points_scoring_chance:'Scores points %',avg_points:'Avg. points',simulated_race_time_seconds:'Race time (s)',delta_vs_baseline_seconds:'Δ baseline (s)',pit_stops:'Stops'};
function format(value,key){if(value===null||value===undefined)return '—';if(typeof value!=='number')return scenarioNames[value]||value;return ['win_chance','podium_chance','dnf_chance','points_chance','top10_chance','points_scoring_chance'].includes(key)?(value*100).toFixed(1):Number.isInteger(value)?String(value):/finish|position/.test(key)?value.toFixed(2):/points/.test(key)?value.toFixed(1):value.toFixed(3);}
async function results(){
  if(!selected)return;const ticket=++loading;
  el('exportCsv').disabled=true;el('exportStatus').hidden=true;
  const data=await client().lab_results(selected,el('driverFilter').value,el('scenarioFilter').value);
  if(ticket!==loading)return;
  options('driverFilter',data.drivers||[],'All drivers',el('driverFilter').value);
  options('scenarioFilter',data.scenarios||[],'All scenarios',el('scenarioFilter').value);
  currentRows=data.rows||[];el('exportCsv').disabled=!currentRows.length;
  el('verification').textContent=data.verification?.status==='PASS'?`✓ ${Number(data.verification.cases_verified).toLocaleString()} cases independently verified`:data.verification?.status==='STALE'?'Verification stale · files changed':'Exploratory results · no accuracy guarantee';
  el('rowCount').textContent=`${currentRows.length} result ${currentRows.length===1?'row':'rows'}`;
  if(!currentRows.length){el('resultTable').innerHTML='<div class="empty">No results for this selection yet. Follow the run log above.</div>';}
  else{const keys=Object.keys(currentRows[0]);el('resultTable').innerHTML=`<table><thead><tr>${keys.map(key=>`<th>${escape(headings[key]||key)}</th>`).join('')}</tr></thead><tbody>${currentRows.map(row=>`<tr>${keys.map(key=>`<td class="${key==='delta_vs_baseline_seconds'?(row[key]<0?'negative':row[key]>0?'positive':''):''}">${escape(format(row[key],key))}</td>`).join('')}</tr>`).join('')}</tbody></table>`;}
  draw(data);
}
function draw(data){
  const canvas=el('lapChart'), ratio=window.devicePixelRatio||1;
  const w=canvas.clientWidth,h=220;canvas.width=w*ratio;canvas.height=h*ratio;
  const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);ctx.clearRect(0,0,w,h);
  const laps=data.laps||[];el('chartEmpty').hidden=Boolean(laps.length||currentRows.length);
  if(!laps.length&&currentRows.length&&'win_chance' in currentRows[0]){
    el('chartTitle').textContent='Win probability';el('chartLegend').textContent='Monte Carlo · saved features';
    const rows=[...currentRows].sort((a,b)=>b.win_chance-a.win_chance).slice(0,10),max=Math.max(.01,...rows.map(r=>r.win_chance));
    rows.forEach((r,i)=>{const y=6+i*21;ctx.fillStyle=token('--muted');ctx.font='11px Segoe UI';ctx.fillText(r.Driver,0,y+12);ctx.fillStyle=token('--accent');ctx.fillRect(42,y,(w-112)*r.win_chance/max,12);ctx.fillStyle=token('--text');ctx.fillText((100*r.win_chance).toFixed(1)+'%',w-52,y+12);});return;
  }
  el('chartTitle').textContent=`Lap-time trace${data.chart_driver?' · '+data.chart_driver:''}`;
  if(!laps.length){el('chartLegend').textContent='Choose a completed run';return;}
  const groups={};laps.forEach(row=>(groups[row.scenario||'baseline']??=[]).push(row));
  const palette=[token('--accent'),token('--blue'),token('--orange')];
  el('chartLegend').innerHTML=Object.keys(groups).map((k,i)=>`<span style="color:${palette[i%palette.length]}">● ${escape(scenarioNames[k]||k)}</span>`).join(' / ');
  const values=laps.map(r=>r.lap_time_seconds),lo=Math.floor(Math.min(...values)-1),hi=Math.ceil(Math.max(...values)+1),maxLap=Math.max(...laps.map(r=>r.lap));
  const x=n=>48+(n-1)/Math.max(1,maxLap-1)*(w-68),y=v=>h-28-(v-lo)/(hi-lo)*(h-46);
  ctx.font='10px Segoe UI';for(let i=0;i<5;i++){const value=lo+(hi-lo)*i/4,yy=y(value);ctx.strokeStyle=token('--line');ctx.beginPath();ctx.moveTo(44,yy);ctx.lineTo(w-10,yy);ctx.stroke();ctx.fillStyle=token('--muted');ctx.fillText(value.toFixed(1)+'s',0,yy+3);}
  [1,Math.round(maxLap/2),maxLap].forEach(lap=>ctx.fillText('Lap '+lap,x(lap)-12,h-6));
  Object.values(groups).forEach((rows,index)=>{ctx.strokeStyle=palette[index%palette.length];ctx.lineWidth=2;ctx.beginPath();rows.sort((a,b)=>a.lap-b.lap).forEach((row,i)=>i?ctx.lineTo(x(row.lap),y(row.lap_time_seconds)):ctx.moveTo(x(row.lap),y(row.lap_time_seconds)));ctx.stroke();});
}
async function boot(){
  if(booted||!client())return;booted=true;
  const year=new Date().getFullYear();for(let y=year;y>=2018;y--)el('historicalYear').add(new Option(String(y),String(y)));el('historicalYear').value=String(year-1);
  el('checkNext').onclick=()=>safely(async()=>{error('');el('checkNext').disabled=true;try{const f=await client().lab_next_race();el('nextRaceInfo').textContent=`${f.year} ${f.event} · ${f.session} inputs · Race ${new Date(f.race_start_utc).toLocaleString()}. Session availability is checked again when you run.`;}finally{el('checkNext').disabled=false;}});
  el('forecastNext').onclick=()=>safely(async()=>{error('');el('forecastNext').disabled=true;try{const job=await client().lab_start({kind:'forecast',...forecastDefaults()});await refresh();await selectRun(job.id);}finally{controls();}});
  el('scoreForecast').onclick=()=>safely(async()=>{error('');const job=await client().lab_start({kind:'score',forecast_id:selected});await refresh();await selectRun(job.id);});
  el('uploadDiscord').onclick=()=>safely(async()=>{if(!window.confirm('Upload this frozen forecast CSV and all available report charts to your configured Discord channel? Successful deliveries will not be sent again.'))return;error('');const job=await client().lab_start({kind:'discord',forecast_id:selected});await refresh();await selectRun(job.id);});
  el('sharePreview').onclick=()=>safely(async()=>{const result=await client().lab_share_export(selected);sharingMessage=`Saved exports/${result.filename}. Review it using Open results folder. Nothing was uploaded.`;el('betaMessage').textContent=sharingMessage;el('betaMessage').hidden=false;});
  el('inputSource').onchange=controls;
  el('loadHistorical').onclick=()=>safely(loadHistorical);
  el('historicalEvent').onchange=historicalSessions;
  el('historicalYear').onchange=()=>{historicalRequest++;historicalLoading=false;historicalEvents=[];el('historicalEvent').replaceChildren(new Option('Click Load races',''));historicalSessions();el('historicalNote').textContent='Click Load races for the selected year.';};
  Object.entries(scenarioNames).filter(([v])=>!['baseline','all'].includes(v)).forEach(([v,label])=>el('experimentScenario').add(new Option(label,v)));
  document.querySelectorAll('.mode').forEach(button=>button.onclick=()=>{kind=button.dataset.kind;document.querySelectorAll('.mode').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-checked',String(b===button));});controls();});
  el('checkSource').onclick=()=>safely(async()=>{error('');await refresh();});el('refreshHistory').onclick=()=>safely(refresh);
  el('launch').onclick=()=>safely(async()=>{error('');el('launch').disabled=true;try{const job=await client().lab_start({kind,source_dir:el('sourceDir').value,input_source:el('inputSource').value,historical:{year:Number(el('historicalYear').value),event:el('historicalEvent').value,session:el('historicalSession').value},n_sims:Number(el('nSims').value),seed:Number(el('seed').value),overtaking_difficulty:Number(el('difficulty').value),scenario:el('experimentScenario').value});await refresh();await selectRun(job.id);}finally{controls();}});
  el('cancel').onclick=()=>safely(async()=>{await client().lab_cancel();await refresh();await status();});
  el('openFolder').onclick=()=>safely(()=>client().lab_open_folder(selected));
  el('reuseInputs').onclick=()=>safely(async()=>{el('sourceDir').value=reusableSource;el('inputSource').value='saved';await refresh();el('inputSource').focus();});
  el('driverFilter').onchange=()=>safely(results);el('scenarioFilter').onchange=()=>safely(results);
  el('exportCsv').onclick=()=>safely(async()=>{const saved=await client().lab_export(selected,el('driverFilter').value,el('scenarioFilter').value);el('exportStatus').textContent=`Saved ${saved.rows} rows to exports/${saved.filename}. Use Open results folder to access the CSV.`;el('exportStatus').hidden=false;});
  await safely(async()=>{await refresh();const recent=appState.history.find(r=>['completed','existing'].includes(r.status))||appState.history[0];if(appState.active_id||recent)await selectRun(appState.active_id||recent.id);});
  async function tick(){await safely(async()=>{if(appState.active_id){await refresh();await status();}});setTimeout(tick,1500);}setTimeout(tick,1500);
  window.addEventListener('resize',()=>safely(results));
}
window.addEventListener('pywebviewready',boot);if(window.f1Api)boot();
