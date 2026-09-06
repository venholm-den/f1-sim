const el = id => document.getElementById(id);
const client = () => window.pywebview?.api || window.f1Api;
const labels = {monte_carlo:'Monte Carlo',lap_dynamics:'Lap dynamics',experiments:'Scenario experiments'};
const scenarioNames = {all:'All 11 scenarios',baseline:'Baseline',stops_0:'Zero stops (diagnostic)',stops_1:'One stop',stops_2:'Two stops',stops_3:'Three stops',pit_early_5:'Pit 5 laps earlier',pit_late_5:'Pit 5 laps later',degradation_low:'Degradation −25%',degradation_high:'Degradation +25%',pit_loss_low:'Pit loss −5 seconds',pit_loss_high:'Pit loss +5 seconds'};
let kind='monte_carlo', selected=null, appState={}, currentRows=[], lastStatus='', booted=false, loading=0;
const escape = value => String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
function error(message){el('error').textContent=message;el('error').hidden=!message;}
async function safely(action){try{await action();}catch(e){error(e.message||String(e));}}
function options(id, values, allLabel, previous){
  const node=el(id);node.replaceChildren(new Option(allLabel,''));
  values.forEach(value=>node.add(new Option(scenarioNames[value]||value,value)));
  node.value=values.includes(previous)?previous:'';
}
function controls(){
  const busy=Boolean(appState.active_id);
  el('launch').disabled=busy||!appState.features||(kind!=='monte_carlo'&&!appState.matlab)||(kind==='experiments'&&!appState.strategies);
  el('launch').innerHTML=`Start ${labels[kind]} <span>→</span>`;
  el('cancel').disabled=!busy;
  el('monteSettings').hidden=kind!=='monte_carlo';el('experimentSettings').hidden=kind!=='experiments';el('lapSettings').hidden=kind!=='lap_dynamics';
  el('assumptions').textContent=kind==='monte_carlo'?'Uses saved features with neutral weather modifiers. For fresh event data and the complete forecast pipeline, use Race Setup.':'Exploratory dynamics with assumed fuel and tyre parameters. Scenario results verify model arithmetic; they are not calibrated race predictions.';
}
function history(){
  el('history').innerHTML=(appState.history||[]).map(run=>`<button class="${run.id===selected?'active':''}" data-id="${escape(run.id)}"><span class="state">${escape(run.status)}</span><strong>${escape(run.label)}</strong><small>${new Date(run.created_at).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})}${run.scenario&&run.kind==='experiments'?' · '+escape(scenarioNames[run.scenario]||run.scenario):''}</small></button>`).join('')||'<p class="muted">No saved runs yet.</p>';
  el('history').querySelectorAll('button').forEach(button=>button.onclick=()=>safely(()=>selectRun(button.dataset.id)));
}
async function refresh(){
  appState=await client().lab_state(el('sourceDir').value);
  el('connection').textContent='Local workspace';el('sourceContext').textContent=appState.context.label;
  el('sourceDetail').textContent=`${appState.context.drivers} drivers · ${appState.features?'Features available':'Features missing'} · ${appState.strategies?'Strategy available':'Strategy missing'}${appState.context.modified?' · Updated '+new Date(appState.context.modified).toLocaleDateString():''}`;
  el('matlabLabel').textContent=appState.matlab?'Installed':'Not found';controls();history();
}
async function selectRun(id){selected=id;lastStatus='';el('driverFilter').value='';el('scenarioFilter').value='';el('openFolder').disabled=false;history();await status();await results();}
async function status(){
  if(!selected)return;
  const id=selected, data=await client().lab_status(id);if(selected!==id)return;
  el('jobTitle').textContent=data.label||appState.history?.find(r=>r.id===id)?.label||'Saved run';
  el('jobStatus').textContent=data.status;el('reviewTitle').textContent=el('jobTitle').textContent;
  const running=['running','cancelling'].includes(data.status);
  el('statusDot').classList.toggle('running',running);
  if(running&&!data.progress)el('progress').removeAttribute('value');
  else el('progress').value=data.progress?100*data.progress[0]/data.progress[1]:['completed','existing'].includes(data.status)?100:0;
  el('progressText').textContent=running?(data.progress?`${data.progress[0]} / ${data.progress[1]} simulations complete`:data.kind==='monte_carlo'?'Running Monte Carlo simulation…':'Starting simulation. MATLAB startup may take a minute.'):(data.status==='failed'?'Run failed. Open the log for the error.':data.status==='cancelled'?'Cancelled. Partial outputs may be available.':data.status==='interrupted'?'Previous app session ended unexpectedly. Partial outputs may be available.':'Saved results available below.');
  el('log').textContent=data.log||'No log was recorded for this earlier run.';
  if(data.status==='failed'){el('log').parentElement.open=true;}
  if(lastStatus&&lastStatus!==data.status&&!running){await refresh();await results();}
  lastStatus=data.status;
}
const headings={Driver:'Driver',Team:'Team',scenario:'Scenario',simulated_rank:'Rank',avg_finish:'Avg. finish',win_chance:'Win %',podium_chance:'Podium %',dnf_chance:'DNF %',avg_points:'Avg. points',simulated_race_time_seconds:'Race time (s)',delta_vs_baseline_seconds:'Δ baseline (s)',pit_stops:'Stops'};
function format(value,key){if(value===null||value===undefined)return '—';if(typeof value!=='number')return scenarioNames[value]||value;return ['win_chance','podium_chance','dnf_chance'].includes(key)?(value*100).toFixed(2):Number.isInteger(value)?String(value):value.toFixed(3);}
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
    rows.forEach((r,i)=>{const y=6+i*21;ctx.fillStyle='#92a2b7';ctx.font='11px Segoe UI';ctx.fillText(r.Driver,0,y+12);ctx.fillStyle='#eeff85';ctx.fillRect(42,y,(w-112)*r.win_chance/max,12);ctx.fillStyle='#e9eef5';ctx.fillText((100*r.win_chance).toFixed(1)+'%',w-52,y+12);});return;
  }
  el('chartTitle').textContent=`Lap-time trace${data.chart_driver?' · '+data.chart_driver:''}`;
  if(!laps.length){el('chartLegend').textContent='Choose a completed run';return;}
  const groups={};laps.forEach(row=>(groups[row.scenario||'baseline']??=[]).push(row));
  const palette=['#eeff85','#67c9ff','#ffab84'];
  el('chartLegend').innerHTML=Object.keys(groups).map((k,i)=>`<span style="color:${palette[i%palette.length]}">● ${escape(scenarioNames[k]||k)}</span>`).join(' / ');
  const values=laps.map(r=>r.lap_time_seconds),lo=Math.floor(Math.min(...values)-1),hi=Math.ceil(Math.max(...values)+1),maxLap=Math.max(...laps.map(r=>r.lap));
  const x=n=>48+(n-1)/Math.max(1,maxLap-1)*(w-68),y=v=>h-28-(v-lo)/(hi-lo)*(h-46);
  ctx.font='10px Segoe UI';for(let i=0;i<5;i++){const value=lo+(hi-lo)*i/4,yy=y(value);ctx.strokeStyle='#27313d';ctx.beginPath();ctx.moveTo(44,yy);ctx.lineTo(w-10,yy);ctx.stroke();ctx.fillStyle='#92a2b7';ctx.fillText(value.toFixed(1)+'s',0,yy+3);}
  [1,Math.round(maxLap/2),maxLap].forEach(lap=>ctx.fillText('Lap '+lap,x(lap)-12,h-6));
  Object.values(groups).forEach((rows,index)=>{ctx.strokeStyle=palette[index%palette.length];ctx.lineWidth=2;ctx.beginPath();rows.sort((a,b)=>a.lap-b.lap).forEach((row,i)=>i?ctx.lineTo(x(row.lap),y(row.lap_time_seconds)):ctx.moveTo(x(row.lap),y(row.lap_time_seconds)));ctx.stroke();});
}
async function boot(){
  if(booted||!client())return;booted=true;
  Object.entries(scenarioNames).filter(([v])=>!['baseline','all'].includes(v)).forEach(([v,label])=>el('experimentScenario').add(new Option(label,v)));
  document.querySelectorAll('.mode').forEach(button=>button.onclick=()=>{kind=button.dataset.kind;document.querySelectorAll('.mode').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-checked',String(b===button));});controls();});
  el('checkSource').onclick=()=>safely(async()=>{error('');await refresh();});el('refreshHistory').onclick=()=>safely(refresh);
  el('launch').onclick=()=>safely(async()=>{error('');el('launch').disabled=true;try{const job=await client().lab_start({kind,source_dir:el('sourceDir').value,n_sims:Number(el('nSims').value),seed:Number(el('seed').value),overtaking_difficulty:Number(el('difficulty').value),scenario:el('experimentScenario').value});await refresh();await selectRun(job.id);}finally{controls();}});
  el('cancel').onclick=()=>safely(async()=>{await client().lab_cancel();await refresh();await status();});
  el('openFolder').onclick=()=>safely(()=>client().lab_open_folder(selected));
  el('driverFilter').onchange=()=>safely(results);el('scenarioFilter').onchange=()=>safely(results);
  el('exportCsv').onclick=()=>safely(async()=>{const saved=await client().lab_export(selected,el('driverFilter').value,el('scenarioFilter').value);el('exportStatus').textContent=`Saved ${saved.rows} rows to exports/${saved.filename}. Use Open results folder to access the CSV.`;el('exportStatus').hidden=false;});
  await safely(async()=>{await refresh();const recent=appState.history.find(r=>['completed','existing'].includes(r.status))||appState.history[0];if(appState.active_id||recent)await selectRun(appState.active_id||recent.id);});
  async function tick(){await safely(async()=>{if(appState.active_id){await refresh();await status();}});setTimeout(tick,1500);}setTimeout(tick,1500);
  window.addEventListener('resize',()=>safely(results));
}
window.addEventListener('pywebviewready',boot);if(window.f1Api)boot();
