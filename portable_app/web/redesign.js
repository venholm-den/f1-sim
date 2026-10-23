// The supplied Nocturne layout uses the existing controls and Python API.
function initRedesign() {
  $('viewTitle').textContent='Race setup';
  document.querySelectorAll('.panel:not(.tyre-board) h2').forEach(el=>el.textContent=el.textContent.toLowerCase().replace(/^./,c=>c.toUpperCase()));
  const nav=document.querySelector('.nav');
  [['Data',['data','historical','training']],['Setup',['setup']],['Analyse',['dashboard','signals','weather','reliability','strategy','fantasy','compare']]].forEach(([name,views],index)=>{
    const group=document.createElement('div');group.className='nav-group';
    group.innerHTML=`<div class="nav-stage"><span>${index+1}</span>${name}</div>`;
    views.forEach(view=>group.append(nav.querySelector(`[data-view="${view}"]`)));nav.append(group);
  });
  nav.append(nav.querySelector('[data-view="settings"]'));
  document.querySelector('.brand').innerHTML='<span class="brand-emblem" data-icon="flag"></span><div><b>Race Simulator</b><small>Monte Carlo workbench</small></div>';
  const workflow=document.createElement('div');workflow.className='workflow';
  workflow.innerHTML='<nav aria-label="Workflow stages" class="workflow-steps"><button data-open-view="data">1 · Data</button><span>›</span><button data-open-view="setup">2 · Setup</button><span>›</span><button data-open-view="setup" id="workflowRun">3 · Run</button><span>›</span><button data-open-view="dashboard">4 · Analyse</button></nav>';
  workflow.append(document.querySelector('.context-strip'));document.querySelector('.main').prepend(workflow);
  const setup=$('view-setup'),layout=setup.querySelector('.setup-layout'),form=$('setupForm');
  const rows=Array.from(form.querySelectorAll('.parameter-row'));
  const card=(title,number,indices)=>{
    const el=document.createElement('section');el.className='panel setup-card';
    el.innerHTML=`<h2><span class="section-number">${number}</span>${title}</h2><div class="setup-fields"></div>`;
    indices.forEach(i=>el.lastElementChild.append(rows[i]));return el;
  };
  const left=document.createElement('div');left.className='setup-left';
  form.replaceChildren(card('Race','01',[0,1,2]),card('Simulation','02',[3,4]),card('Model inputs','03',[5,6,7]));
  layout.prepend(left);left.append(form,setup.querySelector('.advanced'));
  rows[2].classList.add('wide-field');rows[7].classList.add('wide-field');
  rows[1].querySelector('b').textContent='Grand Prix';rows[2].querySelector('b').textContent='Data cutoff session';
  rows[3].querySelector('b').textContent='Race simulations';rows[6].querySelector('b').textContent='Strategy lookback (seasons)';
  $('sessionInput').classList.add('session-select');
  const sessions=document.createElement('div');sessions.id='sessionPills';sessions.className='session-pills';
  sessions.setAttribute('role','group');sessions.setAttribute('aria-label','Data cutoff session');rows[2].append(sessions);
  const presets=document.createElement('div');presets.className='simulation-presets';
  [10000,25000,50000,100000].forEach(value=>{const button=document.createElement('button');button.type='button';button.textContent=`${value/1000}k`;button.addEventListener('click',()=>{$('nSimsInput').value=value;$('nSimsInput').dispatchEvent(new Event('change',{bubbles:true}));});presets.append(button);});rows[3].append(presets);
  const seed=$('seedInput'), seedControl=document.createElement('div');seedControl.className='seed-control';seed.before(seedControl);seedControl.append(seed);
  const shuffle=document.createElement('button');shuffle.type='button';shuffle.textContent='↻';shuffle.title='New random seed';shuffle.setAttribute('aria-label','New random seed');
  shuffle.addEventListener('click',()=>{seed.value=crypto.getRandomValues(new Uint32Array(1))[0];seed.dispatchEvent(new Event('change',{bubbles:true}));});seedControl.append(shuffle);
  ['baselineInput','lookbackInput'].forEach(id=>{
    const input=$(id),control=document.createElement('div');control.className='number-stepper';input.before(control);
    [-1,1].forEach(step=>{const button=document.createElement('button');button.type='button';button.textContent=step<0?'−':'+';button.setAttribute('aria-label',`${step<0?'Decrease':'Increase'} ${input.getAttribute('aria-label')}`);button.addEventListener('click',()=>{input.value=Math.max(Number(input.min),Math.min(Number(input.max),Number(input.value)+step));input.dispatchEvent(new Event('change',{bubbles:true}));});control.append(button);if(step<0)control.append(input);});
  });
  const right=document.createElement('div');right.className='setup-right';
  right.append(setup.querySelector('.track-overview'),setup.querySelector('.weather-preview'),setup.querySelector('.outputs-panel'));
  right.querySelector('.outputs-panel h2').textContent='Save with this run';
  const footer=document.createElement('div');footer.className='run-dock';footer.append(setup.querySelector('.readiness'),$('runButton'));
  layout.replaceChildren(left,right);setup.append(footer);
  const sync=document.createElement('section');sync.className='automation-strip';
  sync.innerHTML='<label class="check"><input id="followPcRuns" class="switch" type="checkbox" checked>Follow PC runs</label><span id="automationStatus" role="status">Looking for completed forecasts…</span><button id="syncPcRuns" class="ghost">Refresh now</button><p id="automationDeliverySummary" class="footnote" role="status"></p>';
  document.querySelector('.topbar').after(sync);
  const settings=document.createElement('section');settings.className='panel automation-settings';
  settings.innerHTML='<h2>PC automated runs</h2><p class="commentary">Completed forecasts update results and the default season, Grand Prix and session. Editing setup pauses following.</p><label class="directory-label">Automation workspace<input id="pcWorkspaceInput" spellcheck="false" aria-label="Automation workspace"></label><button id="savePcWorkspace" class="ghost">Connect workspace</button><p id="automationDetails" class="footnote"></p>';
  $('view-settings').prepend(settings);
  const deliveryPanel=document.createElement('section');deliveryPanel.className='panel';
  deliveryPanel.innerHTML='<h2>Discord delivery and automation</h2><p id="automationHealthStatus" class="commentary" role="status"></p><p class="footnote">Sent means Discord accepted the upload. It does not confirm that a person viewed it. Missing receipts are unknown; uncertain deliveries require review and are never automatically resent. Training does not trigger a Discord post.</p><div id="automationDeliveries" class="table-wrap"></div>';
  settings.after(deliveryPanel);
  document.querySelector('[data-view="dashboard"]').lastChild.textContent='Results';
  const results=document.querySelector('.results-layout'),deeper=document.createElement('section');deeper.className='panel deeper-panel';
  deeper.innerHTML='<h2>Dig deeper</h2>';
  [['signals','Model signals','Pace, grid and uncertainty behind each prediction'],['weather','Weather & reliability','Conditions, disruption and retirement risk'],['strategy','Tyre strategy','Candidate strategies and expected stops'],['fantasy','Fantasy','Expected points and value'],['compare','Compare runs','Changes between saved forecasts']].forEach(([view,label,help])=>{
    const button=document.createElement('button');button.dataset.openView=view;button.innerHTML=`<span><b>${label}</b><small>${help}</small></span><span>›</span>`;deeper.append(button);
  });
  const distribution=$('finishHeatmap').closest('.panel');distribution.classList.add('finish-distribution');results.insertBefore(deeper,distribution);
  const all=document.createElement('button');all.id='showAllColumns';all.className='ghost';all.textContent='Show all columns';$('openDataEditor').before(all);
  all.addEventListener('click',()=>{state.showAllColumns=!state.showAllColumns;all.textContent=state.showAllColumns?'Show key columns':'Show all columns';safeAction(()=>loadDataPreview());});
}

function renderSessionPills() {
  if(!$('sessionPills'))return;
  $('sessionPills').replaceChildren(...Array.from($('sessionInput').options).map(option=>{
    const button=document.createElement('button');button.type='button';button.textContent=option.value;
    button.setAttribute('aria-pressed',String(option.value===$('sessionInput').value));
    button.addEventListener('click',()=>{$('sessionInput').value=option.value;$('sessionInput').dispatchEvent(new Event('change',{bubbles:true}));renderSessionPills();});return button;
  }));
}

function renderAutomationStatus(feed) {
  state.automation=feed;$('followPcRuns').checked=feed.following;
  const latest=feed.latest;
  $('automationStatus').textContent=latest?`${feed.following?'Following':'Paused'} · ${latest.label} · ${new Date(latest.created_at).toLocaleString()}`:feed.pc_available?'No completed, verified forecast found.':'PC automation workspace unavailable.';
  const labels={sent:'Accepted by Discord',pending:'Pending',failed:'Failed',uncertain:'Uncertain — review required',sending:'Interrupted/in progress — review required',not_recorded:'No delivery receipt',unreadable:'Receipt unreadable — review required'};
  const deliveries=feed.deliveries || [];
  const latestDelivery=deliveries[0];
  $('automationDeliverySummary').textContent=latestDelivery?`Latest delivery: ${latestDelivery.label} · ${labels[latestDelivery.status] || latestDelivery.status}${latestDelivery.attempted_at?` · ${new Date(latestDelivery.attempted_at).toLocaleString()}`:''}. Details in Settings.`:'No Discord delivery receipts found. Details in Settings.';
  const health=feed.health || {status:'unknown'};
  $('automationHealthStatus').textContent=`Last automation check: ${health.status}${health.checked_at_utc?` · ${new Date(health.checked_at_utc).toLocaleString()}`:''}.`+
    (health.failures?.length?` Failures: ${health.failures.join(', ')}.`:'')+
    (health.warnings?.length?` Optional checks need attention: ${health.warnings.join(', ')}.`:'');
  renderTable('automationDeliveries',{columns:['Report','Delivery','Last attempt'],rows:deliveries.map(row=>({Report:row.label,Delivery:labels[row.status] || row.status,'Last attempt':row.attempted_at?new Date(row.attempted_at).toLocaleString():'Unknown'}))});
  $('automationDetails').textContent=`${feed.runs.length} verified forecast(s). ${feed.rejected} incomplete or invalid completed bundle(s) skipped. Checked every 15 seconds while this app is open.`;
  if(document.activeElement!==$('pcWorkspaceInput'))$('pcWorkspaceInput').value=feed.pc_workspace;
}

async function applyPcForecast(run) {
  const version=state.followVersion || 0;
  const outputs=await api().automation_load(run.id),events=await api().events_for_year(run.context.year),options=await api().setup_options(run.context.year,run.context.event);
  if(version!==(state.followVersion || 0) || !state.automation?.following || state.manualRunning)return;
  const settings={...readSettings(),...run.context},years=Array.from($('yearInput').options).map(o=>Number(o.value));
  if(!years.includes(settings.year))years.unshift(settings.year);
  if(!events.includes(settings.event))events.push(settings.event);
  if(!options.sessions.includes(settings.session))options.sessions.push(settings.session);
  setOptions($('yearInput'),years,settings.year);setOptions($('eventInput'),events,settings.event);
  writeSettings(settings);applySetupOptions(options,settings.session);
  state.activeOutputDir=outputs.outputDir;state.automationApplied=run.id;state.setupWeather=null;
  renderOutputs(outputs);renderSessionPills();await refreshSetupTrack();
}

async function pollPcRuns(force=false) {
  if(state.automationPolling)return;state.automationPolling=true;
  const version=state.followVersion || 0;
  try {
    const feed=await api().automation_state();
    if(state.automationChanging || version!==(state.followVersion || 0))return;
    renderAutomationStatus(feed);
    if(feed.following && feed.latest && !state.manualRunning && (force || feed.latest.id!==state.automationApplied))await applyPcForecast(feed.latest);
    const reference=feed.fia_reference_sync;
    if(reference?.destination_sha256 && reference.destination_sha256!==state.fiaReferenceVersion){
      state.fiaReferenceVersion=reference.destination_sha256;
      await reloadData(false,true);
      // Refresh freshness warnings even if the session's frozen run is unchanged.
      if(state.activeOutputDir)await refreshOutputs();
    }
  } catch(error) {$('automationStatus').textContent=`PC sync unavailable · ${error.message}`;}
  finally {state.automationPolling=false;}
}

async function setPcFollowing(following,root) {
  state.followVersion=(state.followVersion || 0)+1;state.automationChanging=true;
  if(state.automation)state.automation.following=following;
  try {renderAutomationStatus(await api().automation_preferences(following,root));}
  finally {state.automationChanging=false;}
  if(following)await pollPcRuns(true);
}

function initPcRuns(initial) {
  renderAutomationStatus(initial.automation);state.automationApplied=initial.outputs?.automationRun?.id;
  $('followPcRuns').addEventListener('change',()=>safeAction(()=>setPcFollowing($('followPcRuns').checked)));
  $('syncPcRuns').addEventListener('click',()=>safeAction(()=>pollPcRuns(true)));
  $('savePcWorkspace').addEventListener('click',()=>safeAction(()=>setPcFollowing($('followPcRuns').checked,$('pcWorkspaceInput').value)));
  const pause=()=>{if(state.automation?.following)safeAction(()=>setPcFollowing(false));};
  $('view-setup').addEventListener('input',pause);$('view-setup').addEventListener('change',pause);
  $('sessionInput').addEventListener('change',renderSessionPills);
  state.pcTimer=setInterval(()=>pollPcRuns(),15000);window.addEventListener('focus',()=>pollPcRuns());renderSessionPills();
}
