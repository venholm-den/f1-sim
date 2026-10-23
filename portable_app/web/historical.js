// Season library controls share the existing cancellable desktop job worker.
const archiveState = {years: new Set([new Date().getFullYear()-1]), selectedJob: null, library: null, mode: 'detailed', page: 1};
function renderArchiveAuth(account) {
  $('archiveAuthStatus').textContent=account.message+
    (account.expires_at?` Expires ${new Date(account.expires_at).toLocaleString()}.`:'');
  $('archiveAuthSignIn').textContent=account.status==='waiting'?'REOPEN F1 SIGN-IN':
    account.status==='signed_in'?'SIGN IN AGAIN':'SIGN IN TO F1';
  $('archiveAuthCancel').hidden=account.status!=='waiting';
}
async function refreshArchiveAuth() {
  clearTimeout(archiveState.authTimer);
  const account=await api().historical_auth_state();
  renderArchiveAuth(account);
  // Poll only while the user is signing in. No token or account claims enter JS.
  if(account.status==='waiting')archiveState.authTimer=setTimeout(()=>safeAction(refreshArchiveAuth),2000);
}
function archiveOptions() {
  return {years: [...archiveState.years].sort((a,b)=>a-b), mode: $('archiveMode').value,
    sessions: [...document.querySelectorAll('[name="archiveSession"]:checked')].map(el=>el.value),
    telemetry: $('archiveTelemetry').checked};
}
function archiveSize(bytes) {
  return bytes >= 1024**3 ? `${(bytes/1024**3).toFixed(2)} GB` : `${(bytes/1024**2).toFixed(1)} MB`;
}
function requestWait(timestamp, asOf) {
  if (!Number.isFinite(timestamp)) return 'Unknown';
  const seconds=Math.max(0,Math.ceil(timestamp-asOf));
  return `${seconds<60?`${seconds}s`:`${Math.ceil(seconds/60)}m`} (${new Date(timestamp*1000).toLocaleTimeString()})`;
}
function renderRequestUsage(usage, jobStatus) {
  const available=usage && usage.status!=='unavailable';
  for (const [id,key] of [['archiveRequestsHour','requests_last_hour'],['archiveRequestsJob','requests_job'],
      ['archiveHttpCache','http_cache_hits_job'],['archiveDataCache','data_cache_hits_job']]) {
    $(id).textContent=available?Number(usage[key] || 0).toLocaleString():'—';
  }
  $('archiveRequestStatus').textContent=!available?
    (usage?.reason || 'Monitoring starts with your next download. Earlier requests cannot be counted retrospectively.'):
    usage.status==='recording_degraded'?'Some request observations could not be saved; counts may be incomplete.':
    `Observed historical downloads · measured since ${new Date(usage.monitored_since*1000).toLocaleString()}`;
  const guards=available?(usage.guards || []).filter(g=>g.used>0 || !g.name.startsWith('ergast.com')):[];
  $('archiveRequestGuards').replaceChildren();
  for (const guard of guards) {
    const line=document.createElement('p');line.className='archive-request-guard';
    const window=guard.window_seconds===3600?'hour':`${guard.window_seconds}s`;
    const label=guard.name.startsWith('any API')?'FastF1 shared worker guard':guard.name;
    line.textContent=`${label}: ${guard.used} / ${guard.limit} per ${window} · ${guard.remaining} slots available`+
      (guard.next_slot_at?` · Next slot in ${requestWait(guard.next_slot_at,usage.as_of)}`:
        guard.next_expiry_at?` · Next expiry in ${requestWait(guard.next_expiry_at,usage.as_of)}`:'')+
      (jobStatus==='running'?'':' · Selected worker observation');
    $('archiveRequestGuards').append(line);
  }
  if (available && !guards.length) $('archiveRequestGuards').textContent='Worker allowance unavailable for this FastF1 version.';
  const rows=available?(usage.providers || []).map(row=>({Provider:row.label,
    'Network / last 60m':row.requests_last_hour,'HTTP cache / this job':row.http_cache_hits_job,
    'HTTP errors / this job':row.http_errors_job || 0,
    Cooldown:row.retry_at?`Retry in ${requestWait(row.retry_at,usage.as_of)}`:
      row.rate_limit_seen?'Limit observed; no active Retry-After countdown':'—'})):[];
  renderTable('archiveRequestProviders',{columns:['Provider','Network / last 60m','HTTP cache / this job','HTTP errors / this job','Cooldown'],rows});
}
function renderArchiveYears() {
  const now = archiveState.library?.current_year || new Date().getFullYear();
  const min = $('archiveMode').value === 'detailed' ? 2018 : 1950;
  const years = Array.from({length: now-min+1}, (_,i)=>now-i);
  const hadSelection=archiveState.years.size>0;
  archiveState.years = new Set([...archiveState.years].filter(year=>years.includes(year)));
  if (hadSelection && !archiveState.years.size) archiveState.years.add(now-1);
  for (const id of ['archiveFrom','archiveTo']) {
    const previous = Number($(id).value);
    setOptions($(id), years, years.includes(previous)?previous:now-1);
  }
  const library = archiveState.library?.seasons || [];
  $('archiveYears').innerHTML=years.map(year=>{
    const saved=library.find(item=>item.year===year && item.mode===$('archiveMode').value);
    return `<label class="archive-year"><input type="checkbox" data-archive-year="${year}" ${archiveState.years.has(year)?'checked':''}><span><b>${year}</b><small>${saved?`${saved.sessions} saved`:year===now?'Season in progress':'Not downloaded'}</small></span></label>`;
  }).join('');
  $('archiveYears').querySelectorAll('input').forEach(el=>el.addEventListener('change',()=>{
    el.checked?archiveState.years.add(Number(el.dataset.archiveYear)):archiveState.years.delete(Number(el.dataset.archiveYear)); updateArchiveSelection();
  }));
  const detailed=$('archiveMode').value==='detailed';
  $('archiveSessionOptions').hidden=!detailed;$('archiveTelemetryOption').hidden=!detailed;
  $('archiveCoverageNote').textContent=detailed?'Lap/sector timing, tyre stints, classifications, weather and race-control data where published. Only prior-day, finalised sessions are saved.':'Published race classifications from 1950 onwards. Older seasons do not have FastF1 timing, weather or tyre data.';
  updateArchiveSelection();
}
function updateArchiveSelection() {
  const years=[...archiveState.years].sort((a,b)=>a-b);
  $('archiveSelection').textContent=years.length?`${years.length} season${years.length===1?'':'s'} selected · ${years.join(', ')}`:'Select at least one season.';
  $('archiveStart').disabled=!years.length || Boolean(archiveState.library?.active_id);
}
function renderArchiveInventory() {
  const library=archiveState.library, rows=library.seasons || [];
  $('archivePath').textContent=library.root;
  $('archiveSavedSeasons').textContent=new Set(rows.map(row=>row.year)).size;
  $('archiveSavedSessions').textContent=library.totals.sessions.toLocaleString();
  $('archiveSavedSize').textContent=archiveSize(library.totals.bytes);
  $('archiveFreeSpace').textContent=archiveSize(library.free_bytes);
  renderTable('archiveInventory',{columns:['Season','Dataset','Saved sessions','Needs retry','Lap rows','Result rows','Stored size','Last downloaded'],rows:rows.map(row=>({Season:row.year,Dataset:row.mode==='detailed'?'Detailed sessions':'Race classifications','Saved sessions':row.sessions,'Needs retry':row.needs_retry,'Lap rows':row.lap_rows,'Result rows':row.result_rows,'Stored size':archiveSize(row.bytes),'Last downloaded':row.last_download_utc}))});
  $('archiveInventory').querySelectorAll('tbody tr').forEach((el,i)=>{el.classList.add('selectable-row');el.tabIndex=0;el.setAttribute('role','button');el.setAttribute('aria-label',`Preview ${rows[i].year} ${rows[i].mode}`);const select=()=>safeAction(()=>chooseArchivePreview(rows[i].year,rows[i].mode));el.addEventListener('click',select);el.addEventListener('keydown',event=>{if(event.key==='Enter')select();});});
  const keys=rows.map(row=>`${row.year}:${row.mode}`), selected=$('archivePreviewSeason').value;
  $('archivePreviewSeason').innerHTML=rows.map(row=>`<option value="${row.year}:${row.mode}">${row.year} · ${row.mode==='detailed'?'Detailed':'Classifications'}</option>`).join('');
  if(keys.includes(selected))$('archivePreviewSeason').value=selected;
  $('archivePreviewLoad').disabled=!rows.length;
  renderArchiveYears();
}
async function refreshHistoricalLibrary() {
  await refreshArchiveAuth();
  archiveState.library=await api().historical_state();renderArchiveInventory();
  const jobs=archiveState.library.jobs || [], active=archiveState.library.active_id;
  $('archiveJobs').innerHTML=jobs.map(job=>`<option value="${escapeHtml(job.id)}">${escapeHtml(job.label)} · ${escapeHtml(job.status)}</option>`).join('');
  if(!jobs.some(job=>job.id===archiveState.selectedJob))archiveState.selectedJob=active || jobs[0]?.id || null;
  if(archiveState.selectedJob)$('archiveJobs').value=archiveState.selectedJob;
  const blocked=active && archiveState.library.active_kind!=='historical_download';
  $('archiveBusy').textContent=blocked?'A Simulation Centre job is running. Wait or cancel it there before downloading.':'';
  if(archiveState.selectedJob && jobs.some(job=>job.id===archiveState.selectedJob))await pollHistoricalDownload();
  else renderRequestUsage(null, 'none');
}
async function startHistoricalDownload() {
  $('archiveStart').disabled=true;
  $('archiveJobStatus').textContent='STARTING';
  try {
    const job=await api().historical_start(archiveOptions());archiveState.selectedJob=job.id;
    notify('Historical download started. Completed sessions are saved as it progresses.');
    await refreshHistoricalLibrary();
  } finally {updateArchiveSelection();}
}
async function pollHistoricalDownload() {
  const job=await api().lab_status(archiveState.selectedJob), progress=job.archive_progress || {};
  const running=['running','cancelling'].includes(job.status);
  $('archiveJobStatus').textContent=job.status.replaceAll('_',' ').toUpperCase();
  $('archiveCurrent').textContent=job.status==='cancelling'?'Stopping after the current session; saved data is retained.':progress.current || 'Starting download worker…';
  $('archiveCounts').textContent=`${progress.processed || 0} / ${progress.total || 0} sessions checked · ${progress.downloaded || 0} saved · ${progress.skipped || 0} already stored · ${progress.failed || 0} unavailable · ${progress.incomplete_telemetry || 0} saved without full telemetry`;
  renderRequestUsage(job.request_usage,job.status);
  const bar=$('archiveProgress');bar.max=progress.total || 1;
  if(!progress.total && running)bar.removeAttribute('value');else bar.value=progress.processed || 0;
  $('archiveStop').disabled=!running || job.status==='cancelling' || archiveState.library.active_id!==job.id;
  $('archiveStart').disabled=running || Boolean(archiveState.library.active_id) || !archiveState.years.size;
  $('archiveResume').disabled=running || Boolean(archiveState.library.active_id);
  $('archiveLog').textContent=job.log || 'Waiting for download log…';
  renderTable('archiveErrors',{columns:['year','event','session','message'],rows:(progress.errors || []).slice(-25)});
  $('archiveOutcome').textContent=job.status==='paused'?(progress.pause_reason || 'The provider rate limit paused this download. Wait before resuming; saved sessions will be skipped.'):job.status==='partial'?'Some data was unavailable. Review the errors and resume to retry.':job.status==='completed'?'Download finished. Every saved session has a provenance record and file checksums.':job.status==='no_data'?'No eligible prior-day sessions were found. Select an earlier season or wait for sessions to finish.':job.status==='interrupted'?'The previous app session ended. Resume to keep building from saved sessions.':'';
  clearTimeout(state.archiveTimer);
  if(!running) {
    archiveState.library=await api().historical_state();renderArchiveInventory();
    $('archiveStart').disabled=Boolean(archiveState.library.active_id) || !archiveState.years.size;
    $('archiveResume').disabled=Boolean(archiveState.library.active_id);
    $('archiveStop').disabled=true;
    const selectedOption=$('archiveJobs').selectedOptions[0];
    if(selectedOption)selectedOption.textContent=`${job.label} · ${job.status}`;
  }
  if((running || job.status==='paused') && state.view==='historical')state.archiveTimer=setTimeout(()=>safeAction(pollHistoricalDownload),2000);
}
async function resumeHistoricalDownload() {
  const job=await api().lab_status(archiveState.selectedJob);
  const request=job.archive;
  $('archiveMode').value=request.mode;archiveState.years=new Set(request.years);
  document.querySelectorAll('[name="archiveSession"]').forEach(el=>el.checked=request.sessions.includes(el.value));
  $('archiveTelemetry').checked=request.telemetry;renderArchiveYears();await startHistoricalDownload();
}
async function chooseArchivePreview(year,mode) {
  $('archivePreviewSeason').value=`${year}:${mode}`;
  if(mode==='results')$('archivePreviewTableName').value='results';
  archiveState.page=1;await loadArchivePreview();
}
async function loadArchivePreview(page=archiveState.page) {
  const [year,mode]=$('archivePreviewSeason').value.split(':');if(!year)return;
  const preview=await api().historical_preview(Number(year),mode,$('archivePreviewTableName').value,page);
  archiveState.page=preview.page;archiveState.pages=preview.pages;
  renderTable('archivePreview',preview);
  $('archivePreviewCount').textContent=`${preview.total_rows.toLocaleString()} rows · page ${preview.page} of ${preview.pages}`;
  $('archivePrevious').disabled=preview.page<=1;$('archiveNext').disabled=preview.page>=preview.pages;
}
function initHistoricalLibrary() {
  renderArchiveYears();
  $('archiveAuthSignIn').addEventListener('click',()=>safeAction(async()=>{
    renderArchiveAuth(await api().historical_auth_start());
    await refreshArchiveAuth();
  }));
  $('archiveAuthCancel').addEventListener('click',()=>safeAction(async()=>{
    clearTimeout(archiveState.authTimer);
    renderArchiveAuth(await api().historical_auth_cancel());
  }));
  $('archiveMode').addEventListener('change',renderArchiveYears);
  $('archiveSelectRange').addEventListener('click',()=>{const a=Number($('archiveFrom').value),b=Number($('archiveTo').value);archiveState.years=new Set(Array.from({length:Math.abs(a-b)+1},(_,i)=>Math.min(a,b)+i));renderArchiveYears();});
  $('archiveSelectAll').addEventListener('click',()=>{$('archiveYears').querySelectorAll('input').forEach(el=>{el.checked=true;archiveState.years.add(Number(el.dataset.archiveYear));});updateArchiveSelection();});
  $('archiveSelectNone').addEventListener('click',()=>{archiveState.years.clear();$('archiveYears').querySelectorAll('input').forEach(el=>el.checked=false);updateArchiveSelection();});
  $('archiveStart').addEventListener('click',()=>safeAction(startHistoricalDownload));
  $('archiveRefresh').addEventListener('click',()=>safeAction(refreshHistoricalLibrary));
  $('archiveStop').addEventListener('click',()=>safeAction(async()=>{const job=await api().lab_status(archiveState.selectedJob);if(job.kind!=='historical_download' || archiveState.library.active_id!==job.id)throw Error('Select the active historical download.');await api().lab_cancel();await pollHistoricalDownload();}));
  $('archiveResume').addEventListener('click',()=>safeAction(resumeHistoricalDownload));
  $('archiveJobs').addEventListener('change',()=>safeAction(async()=>{archiveState.selectedJob=$('archiveJobs').value;await pollHistoricalDownload();}));
  $('archiveOpen').addEventListener('click',()=>safeAction(()=>api().historical_open()));
  $('archiveExport').addEventListener('click',()=>safeAction(async()=>{const button=$('archiveExport');button.disabled=true;try{notify('Exporting the selected saved seasons…');const result=await api().historical_export(archiveOptions());notify(`Exported ${result.files.length} CSV files to ${result.folder}. The prediction model is unchanged.`);}finally{button.disabled=false;}}));
  $('archivePreviewLoad').addEventListener('click',()=>safeAction(()=>loadArchivePreview(1)));
  ['archivePreviewSeason','archivePreviewTableName'].forEach(id=>$(id).addEventListener('change',()=>safeAction(()=>loadArchivePreview(1))));
  $('archivePrevious').addEventListener('click',()=>safeAction(()=>loadArchivePreview(archiveState.page-1)));
  $('archiveNext').addEventListener('click',()=>safeAction(()=>loadArchivePreview(archiveState.page+1)));
}
