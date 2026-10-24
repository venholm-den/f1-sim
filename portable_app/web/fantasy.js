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
// Team picker: every legal team is scored by the backend; the page only keeps the lock choices.
const fantasyPicker = {choices:{}, pool:null};
function pickerSettings() { return {...readSettings(), output_dir: state.activeOutputDir || readSettings().output_dir}; }
function renderFantasyPool() {
  const pool=fantasyPicker.pool;
  if(!pool){$('fantasyPool').innerHTML='';return;}
  const chip=a=>{const choice=fantasyPicker.choices[a.code]||'auto';
    return `<button type="button" class="picker-chip ${choice}" data-asset="${escapeHtml(a.code)}" title="${choice==='locked'?'Locked in':choice==='out'?'Left out':'Picker decides'}">${escapeHtml(a.code)}<small>$${Number(a.price).toFixed(1)}m</small></button>`;};
  $('fantasyPool').innerHTML=pool.drivers.map(chip).join('')+pool.constructors.map(chip).join('');
}
function renderFantasyTeams(data) {
  const best=data.teams[0], pts=v=>Number(v).toFixed(1), money=v=>`$${Number(v).toFixed(1)}m`;
  const row=(a,kind)=>`<tr><td>${escapeHtml(a.code)}${a.boosted?'<span class="picker-boost-tag">2×</span>':''}</td><td>${kind}</td><td>${escapeHtml(a.team)}</td><td class="num">${money(a.price)}</td><td class="num">${pts(a.boosted?a.points*data.rules.boost_multiplier:a.points)}</td></tr>`;
  const range=best.range?`<div><small>Simulated range (P10 to P90)</small><strong>${pts(best.range.p10)} to ${pts(best.range.p90)}</strong></div>`:'';
  const stay=data.current, gain=stay?best.expected_points-stay.expected_points:0;
  const plan=stay?`<div><small>Transfers</small><strong>${best.transfers_in.length?`${escapeHtml(best.transfers_out.join(', '))} → ${escapeHtml(best.transfers_in.join(', '))}`:'Keep your team'}</strong>${best.transfer_penalty?`<p class="footnote">Includes a ${pts(best.transfer_penalty)} transfer penalty.</p>`:''}</div>
    <div><small>Versus keeping your team</small><strong>${gain>=0?'+':''}${pts(gain)} pts</strong><p class="footnote">Your team as it stands: ${pts(stay.expected_points)} expected.</p></div>`:'';
  $('fantasyBestTeam').innerHTML=`<div class="table-wrap"><table><thead><tr><th>Asset</th><th>Type</th><th>Team</th><th class="num">Price</th><th class="num">Expected pts</th></tr></thead><tbody>${best.drivers.map(a=>row(a,'Driver')).join('')}${best.constructors.map(a=>row(a,'Constructor')).join('')}</tbody></table></div>
    <div class="picker-totals"><div><small>Expected points${stay?' after penalty':''}</small><strong>${pts(best.expected_points)}</strong></div>${plan}${range}<div><small>Cost / budget left</small><strong>${money(best.cost)} / ${money(best.budget_left)}</strong></div></div>`;
  const alternatives=data.teams.slice(1).map((t,i)=>({Rank:i+2,Drivers:t.drivers.map(a=>a.code+(a.boosted?' (2×)':'')).join(', '),Constructors:t.constructors.map(a=>a.code).join(', '),
    ...(stay?{Transfers:t.transfers_in.length?`${t.transfers_out.join(', ')} → ${t.transfers_in.join(', ')}`:'None'}:{}),
    'Team price':t.cost,'Expected points':t.expected_points,'Behind best (points)':t.expected_points-best.expected_points}));
  renderTable('fantasyAlternatives',{columns:['Rank','Drivers','Constructors',...(stay?['Transfers']:[]),'Team price','Expected points','Behind best (points)'],rows:alternatives});
}
async function pickFantasyTeam() {
  const include=Object.keys(fantasyPicker.choices).filter(k=>fantasyPicker.choices[k]==='locked');
  const exclude=Object.keys(fantasyPicker.choices).filter(k=>fantasyPicker.choices[k]==='out');
  const current=$('fantasyCurrent').value.split(/[\s,]+/).map(c=>c.trim().toUpperCase()).filter(Boolean);
  // With a team entered, the budget is its value plus the bank.
  const budget=current.length?null:numeric($('fantasyBudget').value);
  saveMyFantasyTeam();
  $('fantasyPickStatus').textContent='Scoring every legal team…';
  let data;
  try { data=await api().fantasy_team(pickerSettings(), budget, $('fantasyBoost').checked, include, exclude,
    current, numeric($('fantasyBank').value) ?? 0, numeric($('fantasyFree').value)); }
  catch(error) { $('fantasyBestTeam').innerHTML='';renderTable('fantasyAlternatives',{columns:[],rows:[]});$('fantasyPickStatus').textContent=String(error?.message||error).replace(/^Error:\s*/,'');return; }
  fantasyPicker.pool={drivers:data.drivers,constructors:data.constructors};
  renderFantasyPool();renderFantasyTeams(data);
  const m=data.market;
  $('fantasyPickStatus').textContent=[`Prices: official ${m.season} ${m.event} quote, captured ${new Date(m.captured_at).toLocaleString()}.`,...data.notes].join(' ');
}
const myTeamKey='f1sim.fantasy.myTeam';
function saveMyFantasyTeam() {
  try { localStorage.setItem(myTeamKey,JSON.stringify({team:$('fantasyCurrent').value,bank:$('fantasyBank').value,free:$('fantasyFree').value})); } catch { /* storage blocked */ }
}
function loadMyFantasyTeam() {
  try {
    const saved=JSON.parse(localStorage.getItem(myTeamKey)||'null');
    if(!saved)return;
    $('fantasyCurrent').value=saved.team||'';$('fantasyBank').value=saved.bank||'0';$('fantasyFree').value=saved.free||'2';
    if(saved.team)$('fantasyMine').open=true;
  } catch { /* storage blocked */ }
}
function initFantasyPicker() {
  loadMyFantasyTeam();
  ['fantasyCurrent','fantasyBank','fantasyFree'].forEach(id=>$(id).addEventListener('change',()=>safeAction(pickFantasyTeam)));
  $('fantasyPick').addEventListener('click',()=>safeAction(pickFantasyTeam));
  $('fantasyPool').addEventListener('click',event=>{
    const code=event.target.closest('[data-asset]')?.dataset.asset;if(!code)return;
    const next={auto:'locked',locked:'out',out:'auto'}[fantasyPicker.choices[code]||'auto'];
    if(next==='auto')delete fantasyPicker.choices[code];else fantasyPicker.choices[code]=next;
    renderFantasyPool();safeAction(pickFantasyTeam);
  });
}
