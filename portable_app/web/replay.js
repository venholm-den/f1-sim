// Session replay and lap telemetry review, read from the downloaded historical library.
const replayState = {sessions: [], data: null, t: 0, playing: false, frame: null, focus: null, colours: {}, telemetry: null, hover: null};
const replayPalette = ['#FF8A3D', '#5AA9FF', '#3BE38B', '#FFC300', '#C17BFF', '#FF8A99', '#6FD3D1', '#F08FC0', '#C9D36A', '#A0A7FF', '#D6D6E2'];
// Familiar team colours where the team is known; anyone else takes the next palette colour.
const replayTeamColours = [[/mclaren/i, '#FF8000'], [/ferrari/i, '#E8002D'], [/red bull racing|^red bull$/i, '#3671C6'], [/mercedes/i, '#27F4D2'],
  [/aston martin/i, '#229971'], [/alpine/i, '#0093CC'], [/williams/i, '#64C4FF'], [/haas/i, '#B6BABD'], [/racing bulls|rb f1|visa cash app|alphatauri/i, '#6692FF']];
const trackStatusLabels = {'2': ['Yellow flag', 'yellow'], '4': ['Safety car', 'amber'], '5': ['Red flag', 'red'],
  '6': ['Virtual safety car', 'amber'], '7': ['VSC ending', 'amber']};
const telemetryChannels = [
  {key: 'speed', label: 'Speed', unit: 'km/h', height: 150},
  {key: 'throttle', label: 'Throttle', unit: '%', height: 80, min: 0, max: 100},
  {key: 'brake', label: 'Brake', unit: '', height: 48, min: 0, max: 100, step: true},
  {key: 'gear', label: 'Gear', unit: '', height: 80, min: 0, max: 8, step: true},
  {key: 'delta', label: 'Delta', unit: 's, B − A', height: 100},
];

function lapTime(seconds) {
  if (seconds == null || !Number.isFinite(seconds)) return '—';
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${(seconds - minutes * 60).toFixed(3).padStart(6, '0')}`;
}
function sessionClock(seconds) {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600), m = Math.floor(total / 60) % 60, s = total % 60;
  return `${h ? `${h}:` : ''}${String(m).padStart(h ? 2 : 1, '0')}:${String(s).padStart(2, '0')}`;
}
function replayDriver(number) { return replayState.data.drivers.find((driver) => driver.number === number); }

// Team colours by order of appearance; a second team-mate is drawn dashed.
function assignReplayColours(drivers) {
  const teams = {}, colours = {};
  drivers.forEach((driver) => {
    const team = driver.team || driver.number;
    if (!(team in teams)) {
      const known = replayTeamColours.find(([pattern]) => pattern.test(String(driver.team || '')));
      teams[team] = {colour: known ? known[1] : replayPalette[Object.keys(teams).filter((t) => !teams[t].known).length % replayPalette.length], known: Boolean(known), count: 0};
    }
    colours[driver.number] = {colour: teams[team].colour, dashed: teams[team].count++ > 0};
  });
  return colours;
}

async function refreshReplaySessions() {
  const previous = $('replaySession').value;
  replayState.sessions = (await api().replay_sessions()).sessions;
  const years = [...new Set(replayState.sessions.map((row) => row.year))];
  $('replaySession').innerHTML = years.map((year) => `<optgroup label="${year}">${replayState.sessions.filter((row) => row.year === year)
    .map((row) => `<option value="${escapeHtml(row.id)}">R${row.round} ${escapeHtml(row.event)} · ${escapeHtml(row.session)}${row.telemetry ? '' : ' · timing only'}</option>`).join('')}</optgroup>`).join('');
  if (replayState.sessions.some((row) => row.id === previous)) $('replaySession').value = previous;
  else if (replayState.sessions.length) $('replaySession').value = (replayState.sessions.find((row) => row.telemetry) || replayState.sessions[0]).id;
  $('replayLoad').disabled = !replayState.sessions.length;
  $('replayStatus').textContent = replayState.sessions.length
    ? `${replayState.sessions.length} saved session${replayState.sessions.length === 1 ? '' : 's'}. Sessions marked "timing only" were downloaded without car telemetry.`
    : 'No detailed sessions are saved yet. Download seasons in Historical Data, with "car and position telemetry" ticked for the full replay.';
}

async function loadReplay() {
  pauseReplay();
  $('replayLoad').disabled = true;
  $('replayStatus').textContent = 'Loading the saved session…';
  try {
    const data = await api().replay_load($('replaySession').value);
    replayState.data = data;
    replayState.colours = assignReplayColours(data.drivers);
    replayState.focus = null;
    replayState.t = data.start;
    replayState.orderKey = '';
    $('replayTitle').textContent = `${data.year} ${data.event} · ${data.session}`;
    $('replaySubtitle').textContent = `${data.drivers.length} drivers · ${sessionClock(data.end - data.start)} of timing`;
    $('replayScrub').min = data.start; $('replayScrub').max = data.end; $('replayScrub').step = 0.1;
    $('replayNote').textContent = data.positionsMessage || (data.outline.length ? '' : 'No circuit outline is available for this session.');
    $('lapChartTitle').textContent = data.race ? 'Lap chart' : 'Lap times';
    $('lapChartNote').textContent = data.race ? 'Position at the end of each lap. The top three are in colour; click any driver to highlight them.'
      : 'Representative lap times by lap number (in/out and slow laps hidden). The three fastest are in colour; click any driver to highlight them.';
    $('replayStatus').textContent = data.telemetry ? 'Loaded with car and position telemetry.'
      : 'Loaded from timing data. Car telemetry was not downloaded for this session.';
    buildReplayTrack();
    renderLapChart();
    renderReplayEvents();
    renderReplayFrame(true);
    setupTelemetryPickers();
  } finally {
    $('replayLoad').disabled = !replayState.sessions.length;
  }
}

// Shared projection: archive X/Y to SVG units with north up.
function replayProjection(points) {
  const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
  const minX = Math.min(...xs), maxY = Math.max(...ys);
  const width = Math.max(Math.max(...xs) - minX, 1), height = Math.max(maxY - Math.min(...ys), 1);
  return {project: ([x, y]) => [x - minX, maxY - y], width, height, size: Math.max(width, height)};
}

function buildReplayTrack() {
  const data = replayState.data;
  const outline = data.outline.map((p) => [p.x, p.y]);
  const sampled = Object.values(data.positions).flatMap((frames) => (frames || []).filter((p, i) => p && i % 20 === 0));
  const all = outline.concat(sampled);
  if (!all.length) {
    $('replayTrack').innerHTML = trackMessage('No car positions or circuit outline', 'Use the running order and lap chart, or download this session again with telemetry.');
    replayState.cars = {};
    return;
  }
  const view = replayProjection(all);
  replayState.view = view;
  const pad = view.size * 0.05, radius = view.size * 0.01;
  const path = outline.length ? `<path class="replay-outline" d="M${outline.map((p) => view.project(p).map((v) => v.toFixed(1)).join(' ')).join('L')}Z"/>` : '';
  const cars = data.drivers.filter((driver) => data.positions[driver.number]).map((driver) =>
    `<g class="replay-car" data-number="${escapeHtml(driver.number)}" style="--car:${replayState.colours[driver.number].colour}">` +
    `<circle r="${radius.toFixed(1)}"/><text x="${(radius * 1.5).toFixed(1)}" y="${(radius * 0.5).toFixed(1)}" font-size="${(radius * 1.7).toFixed(1)}">${escapeHtml(driver.code)}</text></g>`).join('');
  $('replayTrack').innerHTML = `<svg viewBox="${-pad} ${-pad} ${view.width + pad * 2} ${view.height + pad * 2}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Car positions on track">${path}${cars}</svg>` +
    (Object.keys(data.positions).length ? '' : `<div class="replay-overlay">${escapeHtml('Car positions not downloaded')}</div>`);
  replayState.cars = Object.fromEntries([...$('replayTrack').querySelectorAll('.replay-car')].map((el) => [el.dataset.number, el]));
  Object.values(replayState.cars).forEach((el) => el.addEventListener('click', () => focusReplayDriver(el.dataset.number)));
}

function positionAt(number, t) {
  const data = replayState.data, frames = data.positions[number];
  if (!frames) return null;
  const f = (t - data.start) / data.step, i = Math.floor(f), a = frames[i], b = frames[i + 1];
  if (!a) return null;
  if (!b) return a;
  return [a[0] + (b[0] - a[0]) * (f - i), a[1] + (b[1] - a[1]) * (f - i)];
}

// Race: laps completed, then who crossed the line first. Other sessions: best lap so far.
function runningOrder(t) {
  const data = replayState.data;
  const rows = data.drivers.map((driver) => {
    const laps = data.laps[driver.number] || [];
    const done = laps.filter((lap) => lap.end != null && lap.end <= t);
    const current = laps.find((lap) => lap.start != null && lap.start <= t && (lap.end == null || lap.end > t));
    const timed = done.filter((lap) => lap.time != null && !lap.deleted);
    const best = timed.length ? Math.min(...timed.map((lap) => lap.time)) : null;
    const last = done[done.length - 1];
    return {driver, completed: last ? last.lap : 0, lastEnd: last?.end ?? Infinity, last: last?.time ?? null, best,
      compound: (current || last)?.compound || '', inPit: Boolean(current?.pitOut && current.start + 5 > t) || Boolean(last?.pitIn && !current)};
  });
  if (data.race) rows.sort((a, b) => b.completed - a.completed || a.lastEnd - b.lastEnd);
  else rows.sort((a, b) => (a.best ?? Infinity) - (b.best ?? Infinity));
  const leader = rows[0];
  rows.forEach((row) => {
    if (row === leader) row.gap = data.race ? (row.completed ? `Lap ${row.completed}` : '—') : row.best == null ? 'No time' : lapTime(row.best);
    else if (data.race) {
      // Gap at the line: seconds behind the leader on the same lap, or laps down.
      const leaderLaps = data.laps[leader.driver.number] || [];
      const sameLap = leaderLaps.find((lap) => lap.lap === row.completed);
      const lapped = leaderLaps.filter((lap) => lap.lap > row.completed && lap.end != null && lap.end <= row.lastEnd).length;
      row.gap = !row.completed || !sameLap ? '—' : lapped ? `+${lapped} L` : `+${(row.lastEnd - sameLap.end).toFixed(1)}s`;
    } else row.gap = row.best == null ? 'No time' : `+${(row.best - leader.best).toFixed(3)}`;
  });
  return rows;
}

function renderReplayOrder(t) {
  const rows = runningOrder(t);
  const key = rows.map((row) => `${row.driver.number}:${row.completed}:${row.gap}:${row.compound}:${row.inPit}`).join('|') + replayState.focus;
  if (key === replayState.orderKey) return;
  replayState.orderKey = key;
  const tyre = (compound) => compound ? `<span class="tyre-dot ${escapeHtml(compound.toLowerCase())}" title="${escapeHtml(compound)}">${escapeHtml(compound[0])}</span>` : '';
  $('replayOrder').innerHTML = `<table><thead><tr><th class="num">Pos</th><th>Driver</th><th class="num">${replayState.data.race ? 'Gap' : 'Best'}</th><th class="num">Last lap</th><th>Tyre</th></tr></thead><tbody>${rows.map((row, index) => {
    const colour = replayState.colours[row.driver.number];
    return `<tr class="selectable-row${replayState.focus === row.driver.number ? ' focused' : ''}" data-number="${escapeHtml(row.driver.number)}" tabindex="0">` +
      `<td class="num">${index + 1}</td><td><span class="driver-swatch${colour.dashed ? ' dashed' : ''}" style="--car:${colour.colour}"></span><b>${escapeHtml(row.driver.code)}</b>${row.inPit ? ' <small class="pit-tag">PIT</small>' : ''}<small class="replay-team">${escapeHtml(row.driver.team)}</small></td>` +
      `<td class="num">${escapeHtml(row.gap)}</td><td class="num">${lapTime(row.last)}</td><td>${tyre(row.compound)}</td></tr>`;
  }).join('')}</tbody></table>`;
  $('replayOrder').querySelectorAll('tr[data-number]').forEach((el) => {
    el.addEventListener('click', () => focusReplayDriver(el.dataset.number));
    el.addEventListener('keydown', (event) => { if (event.key === 'Enter') focusReplayDriver(el.dataset.number); });
  });
}

function trackStatusAt(t) {
  let current = null;
  for (const row of replayState.data.trackStatus) { if (row.t <= t) current = row; else break; }
  return current && trackStatusLabels[current.status];
}

function renderReplayFrame(force = false) {
  const data = replayState.data;
  if (!data) return;
  const t = replayState.t;
  const placed = {};
  for (const [number, el] of Object.entries(replayState.cars || {})) {
    const point = positionAt(number, t);
    el.style.display = point ? '' : 'none';
    if (point) {
      const [x, y] = replayState.view.project(point);
      placed[number] = [x, y];
      el.setAttribute('transform', `translate(${x.toFixed(1)} ${y.toFixed(1)})`);
    }
    el.classList.toggle('focused', replayState.focus === number);
    el.classList.toggle('dimmed', Boolean(replayState.focus) && replayState.focus !== number);
  }
  $('replayScrub').value = t;
  const order = runningOrder(t);
  hideCrowdedLabels(order, placed);
  const totalLaps = Math.max(...Object.values(data.laps).flat().map((lap) => lap.lap));
  $('replayClock').textContent = data.race
    ? `Lap ${Math.min(order[0].completed + 1, totalLaps)}/${totalLaps} · ${sessionClock(t - data.start)}`
    : `${sessionClock(t - data.start)} / ${sessionClock(data.end - data.start)}`;
  const flag = trackStatusAt(t);
  $('replayFlag').hidden = !flag;
  if (flag) { $('replayFlag').textContent = flag[0]; $('replayFlag').dataset.tone = flag[1]; }
  const now = performance.now();
  if (force || !replayState.orderAt || now - replayState.orderAt > 250) { replayState.orderAt = now; renderReplayOrder(t); }
  moveLapCursor(order[0].completed);
  markReplayEvent(t);
}

// Label only the focused car and the top three, and only where the codes do not overlap.
function hideCrowdedLabels(order, placed) {
  const radius = replayState.view.size * 0.01, kept = [];
  const ranked = order.slice(0, 3).map((row) => String(row.driver.number)).filter((number) => placed[number]);
  Object.keys(placed).forEach((number) => replayState.cars[number].classList.add('label-hidden'));
  if (replayState.focus && placed[replayState.focus]) ranked.unshift(String(replayState.focus));
  [...new Set(ranked)].forEach((number) => {
    const [x, y] = placed[number];
    const clash = kept.some(([kx, ky]) => Math.abs(kx - x) < radius * 6 && Math.abs(ky - y) < radius * 2.2);
    replayState.cars[number].classList.toggle('label-hidden', clash);
    if (!clash) kept.push([x, y]);
  });
}

function replayTick(now) {
  if (!replayState.playing) return;
  const elapsed = Math.min(0.25, (now - (replayState.lastTick || now)) / 1000);
  replayState.lastTick = now;
  replayState.t = Math.min(replayState.data.end, replayState.t + elapsed * Number($('replaySpeed').value));
  renderReplayFrame();
  if (replayState.t >= replayState.data.end) pauseReplay();
  else replayState.frame = requestAnimationFrame(replayTick);
}
function playReplay() {
  if (!replayState.data) return;
  if (replayState.t >= replayState.data.end) replayState.t = replayState.data.start;
  replayState.playing = true; replayState.lastTick = null;
  $('replayPlay').textContent = '❚❚'; $('replayPlay').setAttribute('aria-label', 'Pause');
  replayState.frame = requestAnimationFrame(replayTick);
}
function pauseReplay() {
  replayState.playing = false;
  cancelAnimationFrame(replayState.frame);
  $('replayPlay').textContent = '▶'; $('replayPlay').setAttribute('aria-label', 'Play');
}
function stepReplayLap(direction) {
  const data = replayState.data;
  if (!data) return;
  // Jump to the leader's next or previous line crossing.
  const leader = runningOrder(replayState.t)[0].driver.number;
  const ends = (data.laps[leader] || []).map((lap) => lap.end).filter((end) => end != null);
  const target = direction > 0 ? ends.find((end) => end > replayState.t + 0.5) : [...ends].reverse().find((end) => end < replayState.t - 0.5);
  replayState.t = target ?? (direction > 0 ? data.end : data.start);
  renderReplayFrame(true);
}

function focusReplayDriver(number) {
  replayState.focus = replayState.focus === number ? null : number;
  renderReplayFrame(true);
  applyLapChartFocus();
}
// With nobody focused, the chart keeps three drivers in full colour and quietens the rest, so
// the lines stay readable: the top three at the flag in a race, the three fastest laps otherwise.
function riverLeaders(series, race, count = 3) {
  const rank = Object.entries(series).filter(([, values]) => values.length).map(([number, values]) => race
    ? [number, -values[values.length - 1][0], values[values.length - 1][1]]
    : [number, Math.min(...values.map((v) => v[1])), 0]);
  return rank.sort((a, b) => a[1] - b[1] || a[2] - b[2]).slice(0, count).map(([number]) => number);
}
function applyLapChartFocus() {
  const leaders = new Set(replayState.lapLeaders || []);
  $('replayLapChart').querySelectorAll('[data-number]').forEach((el) => {
    el.classList.toggle('focused', el.dataset.number === replayState.focus);
    el.classList.toggle('dimmed', Boolean(replayState.focus) && el.dataset.number !== replayState.focus);
    el.classList.toggle('quiet', !replayState.focus && !leaders.has(el.dataset.number));
  });
}

function lapChartSeries() {
  const data = replayState.data;
  if (data.race) {
    const byLap = {};
    for (const [number, laps] of Object.entries(data.laps)) laps.forEach((lap) => { if (lap.end != null) (byLap[lap.lap] ||= []).push([number, lap.end]); });
    const series = Object.fromEntries(data.drivers.map((driver) => [driver.number, []]));
    for (const [lap, rows] of Object.entries(byLap)) rows.sort((a, b) => a[1] - b[1]).forEach(([number], index) => series[number].push([Number(lap), index + 1]));
    return series;
  }
  const times = Object.values(data.laps).flat().filter((lap) => lap.time != null && !lap.deleted && !lap.pitIn && !lap.pitOut).map((lap) => lap.time);
  const limit = Math.min(...times) * 1.12;
  return Object.fromEntries(data.drivers.map((driver) => [driver.number, (data.laps[driver.number] || [])
    .filter((lap) => lap.time != null && !lap.deleted && !lap.pitIn && !lap.pitOut && lap.time <= limit).map((lap) => [lap.lap, lap.time])]));
}

function renderLapChart() {
  const data = replayState.data, series = lapChartSeries();
  const points = Object.values(series).flat();
  if (!points.length) { $('replayLapChart').innerHTML = '<div class="empty">No timed laps to chart.</div>'; return; }
  const width = Math.max(600, $('replayLapChart').clientWidth || 900), height = data.race ? Math.max(260, data.drivers.length * 18 + 40) : 280;
  const left = 44, right = 56, top = 12, bottom = 28;
  const maxLap = Math.max(...points.map((p) => p[0])), minLap = Math.min(...points.map((p) => p[0]));
  let minY = Math.min(...points.map((p) => p[1])), maxY = Math.max(...points.map((p) => p[1]));
  if (data.race) { minY = 1; maxY = data.drivers.length; }
  const x = (lap) => left + (lap - minLap) / Math.max(1, maxLap - minLap) * (width - left - right);
  const y = (value) => top + (value - minY) / Math.max(1e-9, maxY - minY) * (height - top - bottom);
  const lapTicks = [], every = maxLap > 40 ? 10 : maxLap > 15 ? 5 : 1;
  for (let lap = Math.ceil(minLap / every) * every; lap <= maxLap; lap += every) lapTicks.push(lap);
  const yTicks = data.race ? Array.from({length: data.drivers.length}, (_, i) => i + 1).filter((p) => p === 1 || p % 5 === 0)
    : Array.from({length: 5}, (_, i) => minY + (maxY - minY) * i / 4);
  const grid = lapTicks.map((lap) => `<line class="grid" x1="${x(lap)}" x2="${x(lap)}" y1="${top}" y2="${height - bottom}"/><text class="axis" x="${x(lap)}" y="${height - 8}" text-anchor="middle">${lap}</text>`).join('') +
    yTicks.map((value) => `<line class="grid" x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}"/><text class="axis" x="${left - 6}" y="${y(value) + 4}" text-anchor="end">${data.race ? `P${value}` : lapTime(value).replace(/\.\d+$/, '')}</text>`).join('');
  const lines = data.drivers.map((driver) => {
    const values = series[driver.number] || [];
    if (!values.length) return '';
    const colour = replayState.colours[driver.number], lastPoint = values[values.length - 1];
    return `<g class="lap-line" data-number="${escapeHtml(driver.number)}" style="--car:${colour.colour}"><polyline points="${values.map(([lap, value]) => `${x(lap).toFixed(1)},${y(value).toFixed(1)}`).join(' ')}"${colour.dashed ? ' stroke-dasharray="6 4"' : ''}/>` +
      `<text x="${x(lastPoint[0]) + 6}" y="${y(lastPoint[1]) + 4}">${escapeHtml(driver.code)}</text><title>${escapeHtml(driver.code)} · ${escapeHtml(driver.team)}</title></g>`;
  }).join('');
  $('replayLapChart').innerHTML = `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${data.race ? 'Position by lap' : 'Lap times by lap'}">${grid}<line id="lapCursor" class="lap-cursor" y1="${top}" y2="${height - bottom}"/>${lines}</svg>`;
  replayState.lapX = x;
  replayState.lapLeaders = riverLeaders(series, data.race);
  replayState.lapCursorLap = null;
  $('replayLapChart').querySelectorAll('.lap-line').forEach((el) => el.addEventListener('click', () => focusReplayDriver(el.dataset.number)));
  applyLapChartFocus();
}
function moveLapCursor(completed) {
  const cursor = $('lapCursor');
  if (!cursor || replayState.lapCursorLap === completed) return;
  replayState.lapCursorLap = completed;
  const xpos = replayState.lapX(Math.max(1, completed));
  cursor.setAttribute('x1', xpos); cursor.setAttribute('x2', xpos);
}

// Telemetry review -----------------------------------------------------------
function validLaps(number) {
  return (replayState.data.laps[number] || []).filter((lap) => lap.start != null && lap.end != null && lap.time != null);
}
function fastestLap(number) {
  const laps = validLaps(number).filter((lap) => !lap.deleted && !lap.pitIn && !lap.pitOut);
  return laps.sort((a, b) => a.time - b.time)[0];
}
function fillLapSelect(select, number, chosen) {
  const best = fastestLap(number);
  select.innerHTML = validLaps(number).map((lap) => `<option value="${lap.lap}">Lap ${lap.lap} · ${lapTime(lap.time)}${best && lap.lap === best.lap ? ' ★' : ''}${lap.pitIn || lap.pitOut ? ' · pit' : ''}${lap.deleted ? ' · deleted' : ''}</option>`).join('');
  select.value = chosen ?? best?.lap ?? select.options[0]?.value ?? '';
}
function setupTelemetryPickers() {
  const data = replayState.data;
  const ranked = data.drivers.map((driver) => [driver.number, fastestLap(driver.number)]).filter(([, lap]) => lap).sort((a, b) => a[1].time - b[1].time);
  const options = data.drivers.map((driver) => `<option value="${escapeHtml(driver.number)}">${escapeHtml(driver.code)} · ${escapeHtml(driver.team)}</option>`).join('');
  $('telADriver').innerHTML = options;
  $('telBDriver').innerHTML = '<option value="">None</option>' + options;
  $('telADriver').value = ranked[0]?.[0] || data.drivers[0].number;
  $('telBDriver').value = ranked[1]?.[0] || '';
  fillLapSelect($('telALap'), $('telADriver').value);
  fillLapSelect($('telBLap'), $('telBDriver').value);
  $('telBLap').disabled = !$('telBDriver').value;
  replayState.telemetry = null;
  $('telCharts').innerHTML = ''; $('telTrack').innerHTML = ''; $('telSummary').innerHTML = ''; $('telReadout').innerHTML = '';
  $('telCompare').disabled = !data.telemetry;
  if (data.telemetry) safeAction(loadTelemetry);
  else $('telStatus').textContent = 'Car telemetry was not downloaded for this session. Download it again in Historical Data with "car and position telemetry" ticked.';
}

async function loadTelemetry() {
  const id = replayState.data.id, a = $('telADriver').value, b = $('telBDriver').value;
  $('telStatus').textContent = 'Loading lap telemetry…';
  $('telCompare').disabled = true;
  try {
    const [lapA, lapB] = await Promise.all([api().replay_lap(id, a, Number($('telALap').value)),
      b ? api().replay_lap(id, b, Number($('telBLap').value)) : null]);
    if (replayState.data?.id !== id) return;
    replayState.telemetry = {a: lapA, b: lapB};
    if (lapB) lapA.trace.delta = deltaTrace(lapA, lapB);
    $('telStatus').textContent = '';
    renderTelemetry();
  } catch (error) {
    $('telStatus').textContent = error.message || String(error);
    throw error;
  } finally {
    $('telCompare').disabled = false;
  }
}

function interpolate(xs, ys, x) {
  if (x <= xs[0]) return ys[0];
  if (x >= xs[xs.length - 1]) return ys[ys.length - 1];
  let lo = 0, hi = xs.length - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (xs[mid] <= x) lo = mid; else hi = mid; }
  const f = (x - xs[lo]) / Math.max(1e-9, xs[hi] - xs[lo]);
  return ys[lo] + (ys[hi] - ys[lo]) * f;
}
function nearestIndex(xs, x) {
  let lo = 0, hi = xs.length - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (xs[mid] <= x) lo = mid; else hi = mid; }
  return x - xs[lo] < xs[hi] - x ? lo : hi;
}
// Time gap at each of lap A's distances: positive means lap B is behind.
// B's distance is scaled to A's lap length, and ends at its line crossing, so drift does not pile up at the end.
function deltaTrace(lapA, lapB) {
  const a = lapA.trace, b = lapB.trace;
  const scale = (a.lapDistance || a.distance.at(-1)) / Math.max(1, b.lapDistance || b.distance.at(-1));
  const distance = b.distance.map((d) => d * scale), time = [...b.time];
  if (lapB.lap.time != null && b.lapDistance) { distance.push(b.lapDistance * scale); time.push(lapB.lap.time); }
  return a.distance.map((d, i) => +(interpolate(distance, time, d) - a.time[i]).toFixed(3));
}

function renderTelemetry() {
  const {a, b} = replayState.telemetry;
  const width = Math.max(480, $('telCharts').clientWidth || 800), left = 96, right = 12;
  const maxDistance = Math.max(a.trace.distance.at(-1), b ? b.trace.distance.at(-1) : 0);
  const x = (d) => left + d / maxDistance * (width - left - right);
  replayState.telX = {x, left, right, width, maxDistance};
  const traces = [['a', a], ['b', b]].filter(([, lap]) => lap);
  const charts = telemetryChannels.filter((channel) => channel.key === 'delta' ? b : traces.some(([, lap]) => lap.trace[channel.key])).map((channel) => {
    const height = channel.height, pad = 6;
    const values = channel.key === 'delta' ? a.trace.delta : traces.flatMap(([, lap]) => lap.trace[channel.key] || []).filter((v) => v != null);
    let min = channel.min ?? Math.min(...values), max = channel.max ?? Math.max(...values);
    if (channel.key === 'delta') { const span = Math.max(0.1, ...values.map(Math.abs)); min = -span; max = span; }
    if (max === min) max = min + 1;
    const y = (v) => pad + (1 - (v - min) / (max - min)) * (height - pad * 2);
    const line = (lap, key, distances) => {
      const ys = key === 'delta' ? a.trace.delta : lap.trace[key];
      let d = '';
      ys.forEach((v, i) => { if (v == null) return; const px = x(distances[i]).toFixed(1), py = y(v).toFixed(1); d += d ? (channel.step ? `H${px}V${py}` : `L${px} ${py}`) : `M${px} ${py}`; });
      return d;
    };
    const paths = channel.key === 'delta'
      ? `<line class="zero" x1="${left}" x2="${width - right}" y1="${y(0)}" y2="${y(0)}"/><path class="trace delta" d="${line(a, 'delta', a.trace.distance)}"/>`
      : traces.map(([name, lap]) => lap.trace[channel.key] ? `<path class="trace ${name}" d="${line(lap, channel.key, lap.trace.distance)}"/>` : '').join('');
    const scale = channel.key === 'delta' ? [[max, `+${max.toFixed(2)}`], [min, min.toFixed(2)]] : channel.key === 'brake' ? [] : [[max, Math.round(max)], [min, Math.round(min)]];
    return `<div class="telemetry-chart"><svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" data-channel="${channel.key}" role="img" aria-label="${channel.label} against distance">` +
      `<text class="channel-label" x="4" y="16">${channel.label}</text>${channel.unit ? `<text class="axis" x="4" y="30">${channel.unit}</text>` : ''}` +
      scale.map(([v, label]) => `<text class="axis" x="${left - 6}" y="${y(v) + 4}" text-anchor="end">${label}</text>`).join('') +
      `<rect class="plot" x="${left}" y="0" width="${width - left - right}" height="${height}"/>${paths}<line class="hover-line" y1="0" y2="${height}" x1="-10" x2="-10"/></svg></div>`;
  }).join('');
  const axis = `<div class="telemetry-axis"><svg width="${width}" height="20">${[0, .25, .5, .75, 1].map((f) => `<text class="axis" x="${x(maxDistance * f)}" y="14" text-anchor="${f === 0 ? 'start' : f === 1 ? 'end' : 'middle'}">${Math.round(maxDistance * f)} m</text>`).join('')}</svg></div>`;
  $('telCharts').innerHTML = charts + axis;
  $('telCharts').querySelectorAll('svg[data-channel]').forEach((svg) => {
    svg.addEventListener('mousemove', (event) => {
      const box = svg.getBoundingClientRect();
      const px = (event.clientX - box.left) * width / box.width;
      if (px < left) return;
      hoverTelemetry(Math.min(maxDistance, (px - left) / (width - left - right) * maxDistance));
    });
  });
  renderTelemetryTrack();
  renderTelemetrySummary();
  hoverTelemetry(0);
}

function renderTelemetryTrack() {
  const {a, b} = replayState.telemetry;
  const xy = a.trace.xy;
  replayState.telTrack = null;
  if (!xy) { $('telTrack').innerHTML = trackMessage('No position data for lap A'); return; }
  const delta = a.trace.delta, distances = a.trace.distance, total = distances.at(-1);
  // Mini-sectors coloured by which lap gained time across them.
  const sectors = 25, gain = Array.from({length: sectors}, (_, s) => {
    if (!delta) return 'a';
    const start = interpolate(distances, delta, total * s / sectors), end = interpolate(distances, delta, total * (s + 1) / sectors);
    return end - start >= 0 ? 'a' : 'b';
  });
  const points = xy.map(([px, py], i) => ({x: px, y: py, owner: gain[Math.min(sectors - 1, Math.floor(distances[i] / total * sectors))]}));
  const label = b ? 'Track coloured by the faster lap in each mini-sector' : 'Lap A racing line';
  $('telTrack').innerHTML = trackSvg(points, label, (point) => point.owner === 'a' ? 'var(--blue)' : 'var(--orange)');
  const svg = $('telTrack').querySelector('svg');
  const minX = Math.min(...points.map((p) => p.x)), maxY = Math.max(...points.map((p) => p.y));
  const size = Math.max(Math.max(...points.map((p) => p.x)) - minX, maxY - Math.min(...points.map((p) => p.y)));
  svg.insertAdjacentHTML('beforeend', ['a', 'b'].map((name) => `<circle class="tel-marker ${name}" r="${(size * 0.02).toFixed(1)}" cx="-9999" cy="-9999"/>`).join(''));
  replayState.telTrack = {project: (px, py) => [px - minX, maxY - py]};
}

function renderTelemetrySummary() {
  const {a, b} = replayState.telemetry, code = (lap) => replayDriver(lap.driver)?.code || lap.driver;
  const row = (name, lap) => `<div class="tel-lap ${name}"><span>${name.toUpperCase()} · ${escapeHtml(code(lap))} lap ${lap.lap.lap}</span><strong>${lapTime(lap.lap.time)}</strong>` +
    `<small>Top speed ${Math.round(Math.max(...lap.trace.speed))} km/h · S1 ${lapTime(lap.lap.s1)} · S2 ${lapTime(lap.lap.s2)} · S3 ${lapTime(lap.lap.s3)}</small></div>`;
  const gap = b && a.lap.time != null && b.lap.time != null ? b.lap.time - a.lap.time : null;
  $('telSummary').innerHTML = row('a', a) + (b ? row('b', b) : '') +
    (gap != null ? `<p class="tel-gap">${gap === 0 ? 'Identical lap times' : `${escapeHtml(code(gap > 0 ? a : b))} faster by ${Math.abs(gap).toFixed(3)}s`}</p>` : '') +
    (b ? '<p class="tel-gap">Map: <b class="tel-a">blue</b> where A gains time, <b class="tel-b">orange</b> where B gains.</p>' : '');
}

function hoverTelemetry(distance) {
  const tel = replayState.telemetry;
  if (!tel) return;
  const {x} = replayState.telX, px = x(distance);
  $('telCharts').querySelectorAll('.hover-line').forEach((line) => { line.setAttribute('x1', px); line.setAttribute('x2', px); });
  const readout = [];
  for (const [name, lap] of [['a', tel.a], ['b', tel.b]]) {
    if (!lap) continue;
    const i = nearestIndex(lap.trace.distance, distance), t = lap.trace;
    readout.push(`<div class="${name}"><b>${name.toUpperCase()}</b> ${Math.round(t.speed[i])} km/h · throttle ${t.throttle?.[i] ?? '—'}% · ${t.brake?.[i] ? 'braking' : 'no brake'} · gear ${t.gear?.[i] ?? '—'}${t.drs?.[i] >= 10 ? ' · DRS' : ''}</div>`);
    const marker = $('telTrack').querySelector(`.tel-marker.${name}`);
    if (marker && replayState.telTrack && t.xy) {
      const [mx, my] = replayState.telTrack.project(...t.xy[i]);
      marker.setAttribute('cx', mx); marker.setAttribute('cy', my);
    }
  }
  if (tel.a.trace.delta) readout.push(`<div>Gap at ${Math.round(distance)} m: <b>${interpolate(tel.a.trace.distance, tel.a.trace.delta, distance).toFixed(3)}s</b></div>`);
  $('telReadout').innerHTML = readout.join('');
}

// Race events -----------------------------------------------------------------
// Derived from timing only: track status changes, pit entries, cars that stop
// well before the end, and each new fastest lap. Nothing is inferred beyond that.
const NEUTRALISED = ['4', '5', '6'];
function replayEvents(data) {
  const events = [], code = (number) => data.drivers.find((d) => d.number === number)?.code || number;
  let previous = null;
  for (const row of data.trackStatus || []) {
    if (NEUTRALISED.includes(row.status) && row.status !== previous) {
      const [label, tone] = trackStatusLabels[row.status];
      events.push({t: row.t, kind: 'status', tone, label});
    } else if (row.status === '1' && NEUTRALISED.includes(previous)) events.push({t: row.t, kind: 'green', tone: 'green', label: 'Track clear'});
    previous = row.status;
  }
  const laps = Object.values(data.laps).flat().filter((lap) => lap.time != null);
  const typical = laps.length ? laps.map((lap) => lap.time).sort((a, b) => a - b)[Math.floor(laps.length / 2)] : 90;
  for (const driver of data.drivers) {
    const own = data.laps[driver.number] || [];
    own.forEach((lap, index) => {
      if (!lap.pitIn || lap.end == null) return;
      const next = own[index + 1];
      if (!next) return;
      events.push({t: lap.end, kind: 'pit', number: driver.number, label: `${code(driver.number)} pits`,
        detail: `end of lap ${lap.lap}${next.compound ? ` · onto ${next.compound.toLowerCase()}` : ''}`});
    });
    const last = [...own].reverse().find((lap) => lap.end != null);
    // A lapped car still crosses the line near the end; one that stopped two laps early retired.
    if (data.race && last && last.end < data.end - 2 * typical)
      events.push({t: last.end, kind: 'retired', number: driver.number, label: `${code(driver.number)} stops`, detail: `last timed lap ${last.lap}`});
  }
  if (data.race) {
    let best = Infinity;
    laps.filter((lap) => !lap.deleted && lap.end != null && lap.lap > 1).sort((a, b) => a.end - b.end).forEach((lap) => {
      if (lap.time >= best) return;
      best = lap.time;
      const number = Object.keys(data.laps).find((n) => data.laps[n].includes(lap));
      events.push({t: lap.end, kind: 'fastest', number, label: `${code(number)} fastest lap`, detail: `${lapTime(lap.time)} on lap ${lap.lap}`});
    });
  }
  return events.sort((a, b) => a.t - b.t);
}

function renderReplayEvents() {
  const data = replayState.data, events = replayEvents(data);
  replayState.events = events;
  replayState.eventIndex = -2;
  const span = Math.max(1, data.end - data.start), at = (t) => ((t - data.start) / span * 100).toFixed(2);
  $('replayEvents').innerHTML = events.length ? events.map((event, index) =>
    `<li><button type="button" class="replay-event ${event.kind}" data-index="${index}"${event.number ? ` data-number="${escapeHtml(event.number)}"` : ''}><span class="event-time">${sessionClock(event.t - data.start)}</span><b>${escapeHtml(event.label)}</b>${event.detail ? `<small>${escapeHtml(event.detail)}</small>` : ''}</button></li>`).join('')
    : '<li class="empty">No safety cars, pit stops or retirements in the timing data.</li>';
  // Pins on the scrub bar for the moments that change a race: neutralisations, stops and retirements.
  $('replayPins').innerHTML = events.filter((e) => e.kind !== 'fastest').map((e) => `<i class="pin ${e.kind}" data-tone="${e.tone || ''}" style="left:${at(e.t)}%"></i>`).join('');
  $('replayEvents').querySelectorAll('[data-index]').forEach((el) => el.addEventListener('click', () => {
    const event = events[Number(el.dataset.index)];
    // Start a few seconds early so the moment itself plays.
    replayState.t = Math.max(data.start, event.t - EVENT_LEAD);
    if (event.number && replayState.focus !== event.number) replayState.focus = event.number;
    renderReplayFrame(true); applyLapChartFocus();
  }));
}
// Highlight the latest event at or just ahead of the playhead, without re-rendering the list.
// Jumping to an event starts five seconds early, so look the same distance ahead.
const EVENT_LEAD = 5;
function markReplayEvent(t) {
  const events = replayState.events || [];
  let index = -1;
  for (let i = 0; i < events.length && events[i].t <= t + EVENT_LEAD; i++) index = i;
  if (index === replayState.eventIndex) return;
  replayState.eventIndex = index;
  $('replayEvents').querySelectorAll('.replay-event').forEach((el) => {
    const i = Number(el.dataset.index);
    el.classList.toggle('current', i === index);
    el.classList.toggle('past', i < index);
  });
  const current = $('replayEvents').querySelector('.replay-event.current');
  if (current && replayState.playing) current.scrollIntoView({block: 'nearest'});
}

const replaySpeeds = ['1', '4', '16', '64'];
function replayKey(event) {
  if (state.view !== 'replay' || !replayState.data || event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.target.closest('input:not([type=range]), select, textarea')) return;
  const onScrub = event.target === $('replayScrub');
  // A focused button already toggles on Space; handling it here too would undo the press.
  if (event.key === ' ' && !event.target.closest('button, summary')) { event.preventDefault(); replayState.playing ? pauseReplay() : playReplay(); }
  else if ((event.key === 'ArrowLeft' || event.key === 'ArrowRight') && !onScrub) {
    event.preventDefault();
    const direction = event.key === 'ArrowRight' ? 1 : -1;
    if (event.shiftKey) { replayState.t = Math.min(replayState.data.end, Math.max(replayState.data.start, replayState.t + direction * 10)); renderReplayFrame(true); }
    else stepReplayLap(direction);
  } else if (event.key === ',' || event.key === '.') {
    const at = replaySpeeds.indexOf($('replaySpeed').value);
    $('replaySpeed').value = replaySpeeds[Math.min(replaySpeeds.length - 1, Math.max(0, at + (event.key === '.' ? 1 : -1)))];
  } else if (event.key === 'Escape' && replayState.focus) { replayState.focus = null; renderReplayFrame(true); applyLapChartFocus(); }
}

function initReplay() {
  document.addEventListener('keydown', replayKey);
  $('replayLoad').addEventListener('click', () => safeAction(loadReplay));
  $('replayRefresh').addEventListener('click', () => safeAction(refreshReplaySessions));
  $('replayPlay').addEventListener('click', () => replayState.playing ? pauseReplay() : playReplay());
  $('replayBack').addEventListener('click', () => stepReplayLap(-1));
  $('replayForward').addEventListener('click', () => stepReplayLap(1));
  $('replayScrub').addEventListener('input', () => { if (!replayState.data) return; replayState.t = Number($('replayScrub').value); renderReplayFrame(true); });
  $('telADriver').addEventListener('change', () => fillLapSelect($('telALap'), $('telADriver').value));
  $('telBDriver').addEventListener('change', () => { $('telBLap').disabled = !$('telBDriver').value; fillLapSelect($('telBLap'), $('telBDriver').value); });
  $('telCompare').addEventListener('click', () => safeAction(loadTelemetry));
  let resize;
  window.addEventListener('resize', () => {
    clearTimeout(resize);
    resize = setTimeout(() => { if (state.view !== 'replay' || !replayState.data) return; renderLapChart(); moveLapCursor(runningOrder(replayState.t)[0].completed); if (replayState.telemetry) renderTelemetry(); }, 200);
  });
}

if (typeof module !== 'undefined' && module.exports) module.exports = { replayEvents, riverLeaders };
