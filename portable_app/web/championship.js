// Season title odds; the simulation runs in Python from archived results and the calendar.
const championship = {data:null, request:0};
// A simulated 0 or 1 is not certainty while the title is still mathematically open.
function titleShare(row) {
  if (row.clinched) return 1;
  if (row.eliminated) return 0;
  return Math.min(0.9999, Math.max(0.0001, row.title_chance));
}
function titleStatus(row) { return row.clinched ? 'Clinched' : row.eliminated ? 'Eliminated' : 'In contention'; }
function championshipRows(rows, teamColumn) {
  return rows.map(r=>({
    [teamColumn ? 'Driver' : 'Constructor']:r.name, ...(teamColumn ? {Team:r.team} : {}),
    current_points:r.current_points, wins:r.current_wins, title_chance:titleShare(r), top3_chance:r.top3_chance,
    expected_points:r.expected_points, 'Final points P10–P90':`${Math.round(r.points_p10)}–${Math.round(r.points_p90)}`,
    expected_position:r.expected_position, Status:titleStatus(r)}));
}
function leaderSummary(rows, strongId, noteId) {
  const leader=[...rows].sort((a,b)=>b.current_points-a.current_points)[0];
  const favourite=rows[0];
  $(strongId).textContent=leader ? `${leader.name} · ${leader.current_points} pts` : 'Unknown';
  $(noteId).textContent=!favourite ? '' : favourite.clinched ? 'Title clinched' :
    `${favourite.name} favourite · ${formatCell('title_chance',titleShare(favourite))} title chance`;
}
function renderChampionship() {
  const data=championship.data; if(!data)return;
  const active=data.drivers.filter(r=>r.active!==false);
  $('championshipContext').textContent=`${data.year} · after R${data.last_round} ${data.last_event} · ${plural(data.completed_rounds,'race')} and ${plural(data.completed_sprints,'sprint')} counted`;
  $('championshipWarnings').hidden=!data.warnings.length;
  $('championshipWarnings').textContent=data.warnings.join(' ');
  leaderSummary(data.drivers,'championshipDriverLeader','championshipDriverLeaderNote');
  leaderSummary(data.constructors,'championshipTeamLeader','championshipTeamLeaderNote');
  $('championshipRemaining').textContent=data.remaining_races || data.remaining_sprints ? plural(data.remaining_races,'race') : 'Season complete';
  $('championshipRemainingNote').textContent=data.remaining_sprints ? `plus ${plural(data.remaining_sprints,'sprint')}` : 'No sprints left';
  $('championshipMaxPoints').textContent=String(data.max_points_available);
  const chart=rows=>rows.filter(r=>!r.eliminated).slice(0,8).map(r=>({label:r.name,value:titleShare(r)*100,text:formatCell('title_chance',titleShare(r))}));
  renderBarChart('championshipDriverChart',chart(active),colors.red,{max:100,unit:'%'});
  renderBarChart('championshipTeamChart',chart(data.constructors),colors.blue,{max:100,unit:'%'});
  const driverColumns=['Driver','Team','current_points','wins','title_chance','top3_chance','expected_points','Final points P10–P90','expected_position','Status'];
  renderTable('championshipDriverTable',{columns:driverColumns,rows:championshipRows(active,true)});
  renderTable('championshipTeamTable',{columns:['Constructor',...driverColumns.slice(2)],rows:championshipRows(data.constructors,false)});
  renderTable('championshipCalendar',{columns:['Round','Grand Prix','Date','Sessions'],rows:data.remaining.map(r=>({
    Round:r.round,'Grand Prix':r.event,Date:r.date || '—',Sessions:[r.sprint&&'Sprint',r.race&&'Race'].filter(Boolean).join(' + ')}))},{sortable:false});
  const s=data.settings;
  $('championshipMethod').textContent=`${s.n_sims.toLocaleString()} simulated seasons, calculated ${new Date(data.computed_at).toLocaleString()}. `+
    `Each remaining session redraws every driver's result from their own ${data.year} results (half weight after ${s.form_half_life} rounds; sprints at ${s.sprint_weight}× weight), `+
    `with each team's and driver's form drifting through the rest of the season towards their better or worse results. Retirements come from each driver's own record. `+
    `This is a form model; it does not use the race simulator, grid penalties or circuit traits. Ties are split on wins. Sources: ${data.sources.join(', ') || 'none'}.`;
}
async function refreshChampionship(refresh=false) {
  const request=++championship.request;
  const year=Number($('championshipSeason').value) || null;
  $('championshipRefresh').disabled=true;
  if(!championship.data)$('championshipContext').textContent='Simulating the rest of the season…';
  try {
    const data=await api().championship_odds(year, refresh);
    if(request!==championship.request)return;
    championship.data=data;
    renderChampionship();
  } finally {
    if(request===championship.request)$('championshipRefresh').disabled=false;
  }
}
function initChampionship() {
  const now=new Date().getUTCFullYear();
  setOptions($('championshipSeason'),[now,now-1,now-2].map(String),String(now));
  $('championshipSeason').addEventListener('change',()=>{championship.data=null;safeAction(()=>refreshChampionship());});
  $('championshipRefresh').addEventListener('click',()=>safeAction(()=>refreshChampionship(true)));
}
