// Candidate models use archived qualifying inputs and later race outcomes.
const trainingState = {library:null, years:new Set(), job:null, timer:null};
function trainingOptions(){return {years:[...trainingState.years].sort((a,b)=>a-b),enriched:$('trainingEnriched').checked};}
function updateTrainingSelection(){
  const count=(trainingState.library?.seasons || []).filter(row=>trainingState.years.has(row.year)).reduce((sum,row)=>sum+row.paired_races,0);
  $('trainingSelection').textContent=`${trainingState.years.size} seasons · ${count} matched qualifying + race pairs. Minimum: 3 races.`;
  $('trainingStart').disabled=count<3 || Boolean(trainingState.library?.active_id);
  $('trainingBusy').textContent=trainingState.library?.active_id?'A workspace job is running. Wait for it or stop it on its page.':'';
}
async function refreshModelTraining(){
  trainingState.library=await api().training_state();
  const rows=trainingState.library.seasons;
  $('trainingYears').innerHTML=rows.map(row=>`<label class="archive-year"><input type="checkbox" data-training-year="${row.year}" ${trainingState.years.has(row.year)?'checked':''}><span><b>${row.year}</b><small>${row.paired_races} Q + R pairs · ${row.skipped_races} incomplete</small></span></label>`).join('');
  $('trainingEmpty').hidden=rows.length>0;
  $('trainingYears').querySelectorAll('input').forEach(el=>el.addEventListener('change',()=>{const year=Number(el.dataset.trainingYear);el.checked?trainingState.years.add(year):trainingState.years.delete(year);updateTrainingSelection();}));
  $('trainingPolicy').textContent=trainingState.library.validation_policy;
  const jobs=trainingState.library.jobs;
  $('trainingJobs').innerHTML=jobs.map(job=>`<option value="${escapeHtml(job.id)}">${escapeHtml(job.label)} · ${escapeHtml(job.status)}</option>`).join('');
  if(!jobs.some(job=>job.id===trainingState.job))trainingState.job=jobs[0]?.id || null;
  if(trainingState.job){$('trainingJobs').value=trainingState.job;await pollModelTraining();}
  updateTrainingSelection();
}
async function pollModelTraining(){
  const job=await api().lab_status(trainingState.job), progress=job.training_progress || {}, result=job.training_result;
  const running=['running','cancelling'].includes(job.status);
  $('trainingStatus').textContent=job.status.toUpperCase();
  $('trainingStage').textContent=progress.stage || (running?'Starting training worker…':'Review the job log for details.');
  $('trainingLog').textContent=job.log || 'Waiting for training log…';
  $('trainingStop').disabled=!running || job.status==='cancelling';
  $('trainingOpen').disabled=false;
  $('trainingProgress').max=progress.total || 1;
  if(running && !progress.total)$('trainingProgress').removeAttribute('value');else $('trainingProgress').value=progress.processed || 0;
  const metrics=result?.metrics;
  $('trainingResults').hidden=!result;
  if(metrics){
    renderTable('trainingMetrics',{columns:['Metric','Candidate','Baseline','Meaning'],rows:[
      {Metric:'Finish MAE',Candidate:fmt(metrics.finish_mae,3),Baseline:fmt(metrics.qualifying_baseline_mae,3),Meaning:'Positions; qualifying-order baseline. Lower is better.'},
      {Metric:'Finish RMSE',Candidate:fmt(metrics.finish_rmse,3),Baseline:'—',Meaning:'Positions; weights large errors more heavily.'},
      {Metric:'DNF Brier',Candidate:fmt(metrics.dnf_brier,4),Baseline:fmt(metrics.dnf_prior_baseline_brier,4),Meaning:'Probability error; training DNF-rate baseline. Lower is better.'}
    ]});
    $('trainingCoverage').textContent=`${metrics.train_rows} training driver rows across ${metrics.train_races.length} races · ${metrics.validation_rows} validation rows across ${metrics.validation_races.length} races · ${metrics.excluded_rows_without_qualifying_or_finish} rows without qualifying/finish · ${metrics.excluded_dns_or_disqualified_rows || 0} DNS/disqualified rows excluded · ${metrics.dnf_validation_unknown_rows || 0} unknown validation retirement labels excluded from DNF scoring · finish target: ${metrics.finish_target || 'absolute (older candidate)'}.`;
    $('trainingCandidate').textContent=result.candidate_dir;
    $('trainingVerified').textContent=result.verified?'FILES VERIFIED · CANDIDATE ONLY · NOT ACTIVATED':'FILES CHANGED · DO NOT USE THIS CANDIDATE';
    $('trainingLimitations').textContent=result.limitations;
    if(metrics.feature_coverage){
      const labels={fp1_long_run_relative_pace:'FP1 long runs',fp2_long_run_relative_pace:'FP2 long runs',fp3_long_run_relative_pace:'FP3 long runs',prior_driver_dnf_rate:'Driver reliability',prior_team_dnf_rate:'Team reliability'};
      const coverage=Object.entries(metrics.feature_coverage).filter(([name])=>labels[name]);
      $('trainingLimitations').textContent+=` Inputs: ${metrics.feature_set==='practice_reliability_v1'?'practice + reliability':'qualifying'}. `+coverage.map(([name,c])=>`${labels[name]}: ${c.train}/${metrics.train_rows} training and ${c.validation}/${metrics.validation_rows} validation rows`).join('; ');
    }
    renderTable('trainingRaces',{columns:['Partition','Year','Round','Event'],rows:[...metrics.train_races.map(row=>({Partition:'Training',...row})),...metrics.validation_races.map(row=>({Partition:'Validation',...row}))]});
    renderTable('trainingSkipped',{columns:['year','event','reason'],rows:result.skipped_races});
  }
  const option=$('trainingJobs').selectedOptions[0];if(option)option.textContent=`${job.label} · ${job.status}`;
  clearTimeout(trainingState.timer);
  if(running && state.view==='training')trainingState.timer=setTimeout(()=>safeAction(pollModelTraining),1500);
  if(!running){trainingState.library.active_id=(await api().training_state()).active_id;updateTrainingSelection();}
}
function initModelTraining(){
  $('trainingRefresh').addEventListener('click',()=>safeAction(refreshModelTraining));
  $('trainingJobs').addEventListener('change',()=>safeAction(async()=>{trainingState.job=$('trainingJobs').value;await pollModelTraining();}));
  $('trainingStart').addEventListener('click',()=>safeAction(async()=>{
    $('trainingStart').disabled=true;
    try{const job=await api().training_start(trainingOptions());trainingState.job=job.id;notify('Training started. Each run saves a separate model candidate.');await refreshModelTraining();}
    finally{updateTrainingSelection();}
  }));
  $('trainingStop').addEventListener('click',()=>safeAction(async()=>{
    const active=await api().training_state();if(active.active_id!==trainingState.job)throw Error('Select the active training job.');
    await api().lab_cancel();await pollModelTraining();
  }));
  $('trainingOpen').addEventListener('click',()=>safeAction(()=>api().lab_open_folder(trainingState.job)));
}
