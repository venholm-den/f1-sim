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
const fantasyPicker = {choices:{}, pool:null, best:null};
function pickerSettings() { return {...readSettings(), output_dir: state.activeOutputDir || readSettings().output_dir}; }
function renderFantasyPool() {
  const pool=fantasyPicker.pool;
  if(!pool){$('fantasyPool').innerHTML='';return;}
  const best=new Set([...(fantasyPicker.best?.drivers || []),...(fantasyPicker.best?.constructors || [])].map(a=>a.code));
  const chip=a=>{const choice=fantasyPicker.choices[a.code]||'auto';
    return `<button type="button" class="picker-chip ${choice}${best.has(a.code)?' in-team':''}" data-asset="${escapeHtml(a.code)}" aria-pressed="${choice!=='auto'}" title="${choice==='locked'?'Locked in':choice==='out'?'Left out':'Picker decides'}${best.has(a.code)?' · in the best team':''}"><b>${escapeHtml(a.code)}</b><small>$${Number(a.price).toFixed(1)}m</small><span class="chip-points">${Number(a.points).toFixed(1)}</span></button>`;};
  $('fantasyPool').innerHTML=`<div class="picker-group"><span>Drivers</span>${pool.drivers.map(chip).join('')}</div><div class="picker-group"><span>Constructors</span>${pool.constructors.map(chip).join('')}</div>`;
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
    'Team price':t.cost,'Expected points':t.expected_points,Behind:signedPoints(t.expected_points-best.expected_points)}));
  renderTable('fantasyAlternatives',{columns:['Rank','Drivers','Constructors',...(stay?['Transfers']:[]),'Team price','Expected points','Behind'],rows:alternatives},{sortable:false});
  renderFantasySummary(data);
}
function signedPoints(value) { const n=Number(value); return `${n>0?'+':n<0?'−':''}${Math.abs(n).toFixed(1)} pts`; }

// The answers above the picker, computed from the best team only.
function fantasyAnswers(data) {
  const best=data?.teams?.[0];
  if (!best) return [];
  const money=v=>`$${Number(v).toFixed(1)}m`, boosted=best.drivers.find(a=>a.boosted);
  const answers=[{label:'Best team', value:`${Number(best.expected_points).toFixed(1)} pts`, note:data.current ? 'expected, after transfer penalties' : `expected, within ${money(data.budget)}`}];
  if (best.range) answers.push({label:'Usual range', value:`${Math.round(best.range.p10)}–${Math.round(best.range.p90)}`, note:'P10 to P90 of simulated races'});
  if (boosted) answers.push({label:'Boost', value:`${boosted.code} 2×`, note:`${Number(boosted.points).toFixed(1)} pts doubled`});
  if (data.current) answers.push({label:'Versus your team', value:signedPoints(best.expected_points-data.current.expected_points), note:best.transfers_in.length ? `${best.transfers_in.length} transfer${best.transfers_in.length===1?'':'s'}` : 'keep your team'});
  else answers.push({label:'Spend', value:money(best.cost), note:`${money(best.budget_left)} left`});
  return answers;
}

// Scatter positions in a 0..1 box: x is the P10–P90 spread (risk), y the expected points (reward).
// Without saved floors and ceilings, x falls back to price so the chart still shows value.
function riskRewardPoints(drivers, picked) {
  const usable=(drivers || []).filter(d=>Number.isFinite(Number(d.points)));
  if (usable.length<2) return {mode:'none', points:[]};
  const spread=usable.every(d=>Number.isFinite(Number(d.floor)) && Number.isFinite(Number(d.ceiling)));
  const xs=usable.map(d=>spread ? d.ceiling-d.floor : Number(d.price)), ys=usable.map(d=>Number(d.points));
  const scale=(v,lo,hi)=>hi===lo ? 0.5 : (v-lo)/(hi-lo);
  const [x0,x1,y0,y1]=[Math.min(...xs),Math.max(...xs),Math.min(...ys),Math.max(...ys)];
  return {mode:spread?'spread':'price', xRange:[x0,x1], yRange:[y0,y1], points:usable.map((d,i)=>({code:d.code, x:scale(xs[i],x0,x1), y:scale(ys[i],y0,y1), raw:[xs[i],ys[i]], picked:(picked || []).includes(d.code)}))};
}

function renderRiskReward(data) {
  const best=data.teams[0], picked=best ? best.drivers.map(a=>a.code) : [];
  const chart=riskRewardPoints(data.drivers, picked);
  if (!chart.points.length) { $('fantasyScatter').innerHTML='<div class="empty">Not enough priced drivers to compare.</div>'; return; }
  const W=560, H=320, L=44, R=24, T=14, B=40, px=x=>L+x*(W-L-R), py=y=>H-B-y*(H-T-B);
  const top=new Set([...chart.points].sort((a,b)=>b.raw[1]-a.raw[1]).slice(0,5).map(p=>p.code));
  const unit=chart.mode==='spread' ? 'pts' : '$m', xLabel=chart.mode==='spread' ? 'Spread of simulated scores, P10 to P90 (points)' : 'Price ($m)';
  const ticks=(lo,hi)=>[0,0.5,1].map(t=>({t, v:lo+(hi-lo)*t}));
  const grid=ticks(...chart.yRange).map(({t,v})=>`<line x1="${L}" x2="${W-R}" y1="${py(t)}" y2="${py(t)}"/><text x="${L-6}" y="${py(t)+4}" text-anchor="end">${v.toFixed(0)}</text>`).join('')
    +ticks(...chart.xRange).map(({t,v})=>`<text x="${px(t)}" y="${H-B+16}" text-anchor="middle">${v.toFixed(chart.mode==='spread'?0:1)}</text>`).join('');
  // Label the best team and the top five scorers, skipping any label that would overlap one already placed.
  const placed=[], label=p=>{
    if(!p.picked && !top.has(p.code))return '';
    const right=p.x>0.85, x=px(p.x)+(right?-9:9), y=py(p.y)+4;
    if(placed.some(([qx,qy])=>Math.abs(qx-x)<34 && Math.abs(qy-y)<13))return '';
    placed.push([x,y]);
    return `<text x="${x}" y="${y}" text-anchor="${right?'end':'start'}">${escapeHtml(p.code)}</text>`;
  };
  const ordered=[...chart.points].sort((a,b)=>b.picked-a.picked || b.raw[1]-a.raw[1]), labels=new Map(ordered.map(p=>[p.code,label(p)]));
  const dots=chart.points.sort((a,b)=>a.picked-b.picked).map(p=>`<g class="scatter-point${p.picked?' picked':''}" data-driver="${escapeHtml(p.code)}"><title>${escapeHtml(p.code)}: ${p.raw[1].toFixed(1)} expected pts, ${chart.mode==='spread'?'spread':'price'} ${p.raw[0].toFixed(1)} ${unit}</title><circle cx="${px(p.x)}" cy="${py(p.y)}" r="${p.picked?6:4.5}"/>${labels.get(p.code)}</g>`).join('');
  $('fantasyScatter').innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Expected Fantasy points against ${xLabel.toLowerCase()} for ${chart.points.length} drivers"><g class="scatter-grid">${grid}</g>${dots}<text class="scatter-axis" x="${(L+W-R)/2}" y="${H-6}" text-anchor="middle">${xLabel}</text><text class="scatter-axis" transform="translate(12 ${(T+H-B)/2}) rotate(-90)" text-anchor="middle">Expected points</text></svg>`;
}

function renderFantasySummary(data) {
  const answers=fantasyAnswers(data), best=data.teams[0];
  $('fantasyAnswers').hidden=!answers.length;
  $('fantasyAnswers').innerHTML=answerTiles(answers);
  const budget=Number(best ? best.cost+best.budget_left : data.budget);
  $('fantasySpendFill').style.width=best && budget>0 ? `${Math.min(100,best.cost/budget*100)}%` : '0';
  $('fantasySpend').textContent=best ? `$${best.cost.toFixed(1)}m of $${budget.toFixed(1)}m` : 'No team yet';
  renderRiskReward(data);
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
  catch(error) { $('fantasyBestTeam').innerHTML='';renderTable('fantasyAlternatives',{columns:[],rows:[]});$('fantasyAnswers').hidden=true;$('fantasyScatter').innerHTML='<div class="empty">Pick a team to compare drivers.</div>';$('fantasySpend').textContent='No team yet';$('fantasySpendFill').style.width='0';$('fantasyPickStatus').textContent=String(error?.message||error).replace(/^Error:\s*/,'');return; }
  fantasyPicker.pool={drivers:data.drivers,constructors:data.constructors};fantasyPicker.best=data.teams[0];
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
  ['fantasyCurrent','fantasyBank','fantasyFree','fantasyBudget','fantasyBoost'].forEach(id=>$(id).addEventListener('change',()=>safeAction(pickFantasyTeam)));
  $('fantasyPick').addEventListener('click',()=>safeAction(pickFantasyTeam));
  $('fantasyPool').addEventListener('click',event=>{
    const code=event.target.closest('[data-asset]')?.dataset.asset;if(!code)return;
    const next={auto:'locked',locked:'out',out:'auto'}[fantasyPicker.choices[code]||'auto'];
    if(next==='auto')delete fantasyPicker.choices[code];else fantasyPicker.choices[code]=next;
    renderFantasyPool();safeAction(pickFantasyTeam);
  });
}

if (typeof module !== 'undefined' && module.exports) module.exports = { fantasyAnswers, riskRewardPoints, signedPoints };
