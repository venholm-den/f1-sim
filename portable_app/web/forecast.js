// Weekend hub and the prediction answer row. Every answer is computed from the saved
// run, the saved weekend briefing or the championship odds; none is written by hand.

const hub = {schedule:null, scheduleKey:'', request:0, championshipError:''};

function finite(value) { return value != null && value !== '' && Number.isFinite(Number(value)); }
function wholePct(value) { const n=Number(value)*100; return n>0 && n<0.5 ? '<1%' : `${Math.round(n)}%`; }
function byWinChance(rows) { return rows.filter(r=>finite(r.win_chance)).sort((a,b)=>Number(b.win_chance)-Number(a.win_chance)); }

// Four plain answers for the prediction screen, from the summary rows and finish ranges.
function forecastAnswers(rows, ranges) {
  const ranked=byWinChance(rows || []);
  if (!ranked.length) return [];
  const favourite=ranked[0], win=Math.round(Number(favourite.win_chance)*100);
  const answers=[{label:'Most likely winner', value:`${favourite.Driver} · ${wholePct(favourite.win_chance)}`,
    note:`someone else wins ${100-win}% of simulated races`}];
  const byAverage=(rows || []).filter(r=>finite(r.avg_finish)).sort((a,b)=>Number(a.avg_finish)-Number(b.avg_finish));
  if (byAverage.length>=3) answers.push({label:'Likely podium', value:byAverage.slice(0,3).map(r=>r.Driver).join(' · '), note:'best three average finishes'});
  const widest=(ranges || []).slice(0,8).reduce((best,r)=>!best || r.p75-r.p25>best.p75-best.p25 ? r : best, null);
  if (widest) answers.push({label:'Widest range · top 8', value:`${widest.driver} · P${Math.round(widest.p25)}–P${Math.round(widest.p75)}`, note:'middle half of simulated finishes'});
  if (finite(favourite.dnf_chance)) answers.push({label:'Retirement risk', value:wholePct(favourite.dnf_chance), note:`${favourite.Driver}'s chance of not finishing`});
  return answers;
}

// The hub's answers: who is favourite, how open it is, the title fight and what the forecast is built on.
function hubAnswers(rows, championshipData, run) {
  const ranked=byWinChance(rows || []), answers=[];
  if (ranked.length) {
    answers.push({label:'Favourite', value:ranked[0].Driver, note:`wins ${wholePct(ranked[0].win_chance)} of simulated races`});
    const contenders=ranked.filter(r=>Number(r.win_chance)>=0.15).length;
    answers.push({label:'Contenders', value:String(contenders), note:`${contenders===1?'driver':'drivers'} with at least a 15% win chance`});
  } else {
    answers.push({label:'Favourite', value:'No forecast', note:'run a simulation to see who can win'});
  }
  const drivers=championshipData?.drivers || [];
  if (drivers.length) {
    const leader=[...drivers].sort((a,b)=>b.current_points-a.current_points)[0];
    const favourite=drivers[0];
    answers.push({label:'Championship leader', value:`${leader.name} · ${leader.current_points} pts`,
      note:favourite.clinched ? 'title clinched' : `${favourite.name} has the best title chance`});
  } else {
    answers.push({label:'Championship leader', value:'—', note:championshipData===null ? 'title odds unavailable' : 'loading title odds…'});
  }
  if (ranked.length) answers.push({label:'Forecast', value:run.sims ? `${Number(run.sims).toLocaleString('en-GB')} races` : 'Saved run', note:run.label});
  return answers;
}

// Fifty equally likely finishing positions for one driver, read from P1..Pn probabilities.
// Each dot is the position at the middle of its 2% slice of simulated races.
function quantileDots(probabilities, count=50) {
  const total=probabilities.reduce((sum,p)=>sum+(Number(p)||0),0);
  if (!(total>0)) return [];
  const dots=[];
  let position=0, cumulative=Number(probabilities[0])||0;
  for (let i=0;i<count;i++) {
    const target=(i+0.5)/count*total;
    while (cumulative<target && position<probabilities.length-1) cumulative+=Number(probabilities[++position])||0;
    dots.push(position+1);
  }
  return dots;
}

// The next session that has not started yet, or null once the weekend is over.
function nextSession(sessions, now=Date.now()) {
  return (sessions || []).find(s=>Date.parse(s.start_utc)>now) || null;
}

function answerTiles(answers) {
  return answers.map(a=>`<div class="answer"><span>${escapeHtml(a.label)}</span><b title="${escapeHtml(a.value)}">${escapeHtml(a.value)}</b><small>${escapeHtml(a.note || '')}</small></div>`).join('');
}

function renderDots(targetId, rows, matrix, limit) {
  const target=$(targetId);
  const fields=(matrix?.columns || []).filter(key=>/^P\d+$/.test(key));
  const picks=byWinChance(rows).slice(0,limit).map(r=>({driver:r.Driver, row:(matrix?.rows || []).find(m=>m.Driver===r.Driver)})).filter(p=>p.row);
  if (!fields.length || !picks.length) { target.innerHTML=`<div class="empty">${rows.length ? 'The finish distribution was not saved for this run.' : 'Run a simulation to see where drivers finish.'}</div>`; return; }
  const ticks=new Set([1,3,5,10,15,20,fields.length]);
  target.innerHTML=picks.map(({driver,row})=>{
    const dots=quantileDots(fields.map(key=>row[key]));
    const counts=fields.map((_,i)=>dots.filter(d=>d===i+1).length);
    return `<div class="dot-row" data-driver="${escapeHtml(driver)}" role="img" aria-label="${escapeHtml(driver)}: ${counts.map((c,i)=>c?`P${i+1} ${c*2}%`:'').filter(Boolean).join(', ')}"><b>${escapeHtml(driver)}</b><div class="dot-grid" style="--positions:${fields.length}">${counts.map(c=>`<span>${'<i></i>'.repeat(c)}</span>`).join('')}</div></div>`;
  }).join('')+`<div class="dot-axis" aria-hidden="true" style="--positions:${fields.length}">${fields.map((_,i)=>`<span>${ticks.has(i+1)?`P${i+1}`:''}</span>`).join('')}</div>`;
}

function savedRunLabel() {
  const saved=state.outputs.savedContext || {}, settings=readSettings();
  return {year:saved.year || settings.year, event:displayEventName(saved.event || settings.event), session:saved.session || settings.session};
}

function renderSchedule() {
  const target=$('hubSchedule'), briefing=hub.schedule;
  if (!briefing) {
    target.innerHTML='<div class="empty">Session times appear here once the weekend briefing has run for this Grand Prix.</div>';
    return;
  }
  const next=nextSession(briefing.sessions);
  target.innerHTML=`<p class="hub-schedule-meta">Round ${escapeHtml(briefing.round)} · ${escapeHtml(briefing.format)} weekend${briefing.track?.circuit_name?` · ${escapeHtml(briefing.track.circuit_name)}`:''}</p><ol class="hub-sessions">${briefing.sessions.map(s=>{
    const done=Date.parse(s.start_utc)<=Date.now();
    return `<li class="${s===next?'next':done?'done':''}"><b>${escapeHtml(s.name)}</b><span>${escapeHtml(s.uk_date)}</span><span>${escapeHtml(s.uk_time)}</span>${s===next?'<em>Next</em>':''}</li>`;
  }).join('')}</ol><p class="footnote">UK times from the saved FastF1 schedule.</p>`;
}

function renderHubChampionship() {
  const data=championship.data;
  if (!data) { $('hubChampionship').innerHTML=`<div class="empty">${escapeHtml(hub.championshipError || 'Simulating the rest of the season…')}</div>`; return; }
  const rows=data.drivers.filter(r=>r.active!==false && !r.eliminated).slice(0,5);
  renderBarChart('hubChampionship',rows.map(r=>({label:r.name,value:titleShare(r)*100,text:formatCell('title_chance',titleShare(r))})),colors.red,{max:100,unit:'%'});
  $('hubChampionshipNote').textContent=`${data.year} title chance after R${data.last_round} ${data.last_event}.`;
}

function renderHub() {
  const rows=state.outputs.summaryTable?.rows || [], details=state.outputs.details || {}, context=savedRunLabel();
  const sims=details.run?.settings?.n_sims || details.forecastRun?.n_sims;
  $('hubAnswers').innerHTML=answerTiles(hubAnswers(rows, hub.championshipError ? null : championship.data || undefined, {sims, label:`${context.year} ${context.event} · ${context.session}`}));
  $('hubEvent').textContent=`${context.year} ${context.event}`;
  renderDots('hubDots', rows, details.positionMatrix, 4);
  renderBarChart('hubWin', byWinChance(rows).slice(0,8).map(r=>({label:r.Driver,value:Number(r.win_chance)*100,text:wholePct(r.win_chance)})), colors.red, {max:Math.max(10,...rows.map(r=>Number(r.win_chance)*100||0))});
  renderSchedule();
  renderHubChampionship();
}

function renderPredictAnswers() {
  const answers=forecastAnswers(state.outputs.summaryTable?.rows, state.outputs.finishRanges);
  $('predictAnswers').hidden=!answers.length;
  $('predictAnswers').innerHTML=answerTiles(answers);
}

function renderForecastViews() { renderPredictAnswers(); renderHub(); }

async function refreshHub() {
  const request=++hub.request, context=savedRunLabel(), key=`${context.year}|${context.event}`;
  renderHub();
  const jobs=[];
  if (key!==hub.scheduleKey) jobs.push(api().weekend_schedule(context.year, context.event).then(result=>{
    if (request!==hub.request) return;
    hub.schedule=result; hub.scheduleKey=key; renderSchedule();
  }));
  // A missing season archive is normal on a fresh install; the panel says so instead of raising a toast.
  if (!championship.data) jobs.push(refreshChampionship().then(()=>{ hub.championshipError=''; }, error=>{ hub.championshipError=error.message || 'Title odds could not be calculated.'; }).finally(()=>{ if (request===hub.request) renderHub(); }));
  await Promise.all(jobs);
}

if (typeof module !== 'undefined' && module.exports) module.exports = { forecastAnswers, hubAnswers, quantileDots, nextSession };
