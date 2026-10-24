// Collected actual Fantasy scores are separate from the simulation's scoring model.
const fantasyArchive = {data:null, timer:null, request:0};
async function refreshFantasyArchive(year) {
  clearTimeout(fantasyArchive.timer);
  const request=++fantasyArchive.request;
  const data=await api().fantasy_state(year || $('fantasySeason').value || null);
  if(request!==fantasyArchive.request)return;
  fantasyArchive.data=data;
  setOptions($('fantasySeason'),data.supported_seasons,data.year);
  const selected=$('fantasyRound').value;
  $('fantasyRound').innerHTML=data.events.map(e=>`<option value="${e.round}">R${e.round} · ${escapeHtml(e.event)}</option>`).join('');
  if(data.events.some(e=>String(e.round)===selected))$('fantasyRound').value=selected;
  else if(data.events.length)$('fantasyRound').value=String(data.events.at(-1).round);
  const failures=Object.entries(data.attempts).filter(([,v])=>v.status==='error').map(([k])=>k);
  const last=data.market[0];
  $('fantasyArchiveStatus').textContent=data.progress.running ? 'Collecting public feeds…' :
    `${data.completed_weeks} completed weekends · ${data.total_rows.toLocaleString()} source records · ${data.seasons.join(', ') || 'No seasons downloaded'}${failures.length ? ' · Sources need retry: '+failures.join(', ') : ''}${data.errors.length ? ' · '+data.errors.join('; ') : ''}`;
  $('fantasyOpenArchive').title=data.archive;
  $('fantasyMarketContext').textContent=last ? `${last.season} ${last.event} · official feed quote captured ${new Date(last.captured_at).toLocaleString()} · ${last.points_status} points` : 'No official market captured yet. Refresh to download current public data.';
  $('fantasyRefresh').disabled=data.progress.running;
  $('fantasyBackfill').disabled=data.progress.running;
  renderFantasyArchive();
  const market=data.market.map(r=>({Asset:r.name || r.code,Type:r.asset_type,Price:r.price,'Season points':r.season_points}));
  renderTable('fantasyMarketTable',{columns:['Asset','Type','Price','Season points'],rows:market});
  if(state.view==='fantasy')fantasyArchive.timer=setTimeout(()=>safeAction(()=>refreshFantasyArchive()),data.progress.running?2000:15000);
}
function renderFantasyArchive() {
  const data=fantasyArchive.data;if(!data)return;
  const round=$('fantasyRound').value, kind=$('fantasyAssetType').value, source=$('fantasySource').value;
  const rows=data.rows.filter(r=>String(r.round)===round && (kind==='all'||r.asset_type===kind) && (source==='all'||r.source===source))
    .sort((a,b)=>(numeric(b.actual_points) ?? -Infinity)-(numeric(a.actual_points) ?? -Infinity));
  const display=rows.map(r=>({Asset:r.code,Type:r.asset_type,Team:r.team,Price:r.price,
    'Price change':r.price_change,'Actual points':r.actual_points,Status:r.points_status,
    Qualifying:r.qualifying_points,Sprint:r.sprint_points,Race:r.race_points,
    Source:r.source==='official'?'Official F1':'F1 Fantasy Tools',Captured:new Date(r.captured_at).toLocaleString()}));
  renderTable('fantasyActualTable',{columns:['Asset','Type','Team','Price','Price change','Actual points','Status','Qualifying','Sprint','Race','Source','Captured'],rows:display});
  $('fantasyRoundContext').textContent=rows.length ? `${data.year} · ${rows[0].event} · ${rows.length} source records. Source round prices are archived as reported; their timing is not assumed to be pre-race.` : 'No records for this selection. Download this season or change the source filter.';
}
async function collectFantasyArchive(allYears=false) {
  const years=allYears ? fantasyArchive.data.supported_seasons : [Number($('fantasySeason').value)];
  await api().fantasy_refresh(years);
  await refreshFantasyArchive();
}
function initFantasyArchive() {
  $('fantasySeason').addEventListener('change',()=>safeAction(()=>refreshFantasyArchive(Number($('fantasySeason').value))));
  ['fantasyRound','fantasyAssetType','fantasySource'].forEach(id=>$(id).addEventListener('change',renderFantasyArchive));
  $('fantasyRefresh').addEventListener('click',()=>safeAction(()=>collectFantasyArchive(false)));
  $('fantasyBackfill').addEventListener('click',()=>safeAction(()=>collectFantasyArchive(true)));
  $('fantasyOpenArchive').addEventListener('click',()=>safeAction(()=>api().fantasy_open()));
}
