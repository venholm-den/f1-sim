// Setup shortcuts and PC forecast following for the Workbench. The layout itself lives in index.html.
function initSetupControls() {
  const changed=input=>input.dispatchEvent(new Event('change',{bubbles:true}));
  document.querySelectorAll('[data-sims]').forEach(button=>button.addEventListener('click',()=>{$('nSimsInput').value=button.dataset.sims;changed($('nSimsInput'));}));
  $('seedShuffle').addEventListener('click',()=>{$('seedInput').value=crypto.getRandomValues(new Uint32Array(1))[0];changed($('seedInput'));});
  document.querySelectorAll('[data-step-for]').forEach(button=>button.addEventListener('click',()=>{
    const input=$(button.dataset.stepFor);
    input.value=Math.max(Number(input.min),Math.min(Number(input.max),Number(input.value)+Number(button.dataset.step)));changed(input);
  }));
  $('showAllColumns').addEventListener('click',()=>{state.showAllColumns=!state.showAllColumns;$('showAllColumns').textContent=state.showAllColumns?'Show key columns':'Show all columns';safeAction(()=>loadDataPreview());});
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
  // Without a workspace there is nothing to follow: show it as off, not on.
  document.querySelector('.automation-strip').classList.toggle('unavailable',!feed.pc_available);
  $('followPcRuns').disabled=!feed.pc_available;
  if(!feed.pc_available)$('followPcRuns').checked=false;
  $('automationStatus').textContent=latest?`${feed.following?'Following':'Paused'} · ${latest.label} · ${new Date(latest.created_at).toLocaleString()}`:feed.pc_available?'No completed, verified forecast found.':'No PC automation workspace connected. Set one up in Settings.';
  const labels={sent:'Accepted by Discord',pending:'Pending',failed:'Failed',uncertain:'Uncertain — review required',sending:'Interrupted/in progress — review required',not_recorded:'No delivery receipt',unreadable:'Receipt unreadable — review required'};
  const deliveries=feed.deliveries || [];
  const latestDelivery=deliveries[0];
  $('automationDeliverySummary').textContent=latestDelivery?`Latest delivery: ${latestDelivery.label} · ${labels[latestDelivery.status] || latestDelivery.status}${latestDelivery.attempted_at?` · ${new Date(latestDelivery.attempted_at).toLocaleString()}`:''}. Details in Settings.`:feed.pc_available?'No Discord delivery receipts yet.':'';
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
