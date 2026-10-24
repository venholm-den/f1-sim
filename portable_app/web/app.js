const state = {
  settings: {},
  outputs: {},
  statusTimer: null,
  view: 'setup',
  activeOutputDir: null,
};

// Chart colours resolve to the stylesheet's tokens.
const colors = {
  red: "var(--red)",
  amber: "var(--amber)",
  blue: "var(--blue)",
  green: "var(--green)",
  muted: "var(--subtle)",
  orange: "var(--orange)",
};

function api() {
  if (window.pywebview && window.pywebview.api) {
    return window.pywebview.api;
  }
  if (window.f1Api) return window.f1Api;
  throw new Error("pywebview API is not available");
}

function $(id) {
  return document.getElementById(id);
}

// "latest" is a selector, not a race name; show what it currently resolves to.
function displayEventName(event) {
  return event === "latest" ? state.setupOptions?.trackProfile?.event || "Latest eligible event" : event;
}

function setOptions(select, values, selected) {
  select.innerHTML = "";
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
  select.value = selected;
}

function selectedOption(select) {
  const option = select.options[select.selectedIndex];
  return (option && option.value) || select.value || "";
}

function setOvertakingPercent(percent) {
  const value = Math.max(0, Math.min(100, Math.round(Number(percent) || 0)));
  $("overtakingInput").value = value;
  $("overtakingValue").textContent = `${value}%`;
}

function updateOvertakingValue() {
  setOvertakingPercent($("overtakingInput").value);
}

function applySetupOptions(setupOptions, preferredSession) {
  const options = setupOptions || {};
  const sessions = options.sessions || [];
  const selectedSession = sessions.includes(preferredSession) ? preferredSession : sessions[0] || "PRE";
  setOptions($("sessionInput"), sessions, selectedSession);

  const trackProfile = options.trackProfile || {};
  state.setupOptions = options;
  const latestOption = Array.from($("eventInput").options).find((option) => option.value === "latest");
  if (latestOption) latestOption.textContent = $("eventInput").value === "latest" && trackProfile.event ? `Latest · ${trackProfile.event}` : "Latest eligible event";
  if (typeof renderSessionPills === 'function') renderSessionPills();
  const overtakingDifficulty = Number(trackProfile.overtaking_difficulty);
  if (Number.isFinite(overtakingDifficulty)) {
    setOvertakingPercent(overtakingDifficulty * 100);
  }
  $("overtakingDefault").textContent = Number.isFinite(overtakingDifficulty) ? `Track default ${Math.round(overtakingDifficulty * 100)}%` : "";
}

async function refreshSetupOptions(preferredSession) {
  const request = state.setupOptionsRequest = (state.setupOptionsRequest || 0) + 1;
  state.setupTrack={status:'loading',points:[],message:'Loading the selected race and its downloaded geometry…'};
  drawSetupTrack(state.setupOptions?.trackProfile || {});
  const setupOptions = await api().setup_options(Number($("yearInput").value), selectedOption($("eventInput")));
  if(request !== state.setupOptionsRequest)return;
  applySetupOptions(setupOptions, preferredSession);
  state.settings = readSettings();
  updateContext();
  await refreshSetupTrack();
}

function readSettings() {
  return {
    year: Number($("yearInput").value),
    event: selectedOption($("eventInput")) || "latest",
    session: $("sessionInput").value || "Q",
    n_sims: Number($("nSimsInput").value || 1),
    random_seed: Number($("seedInput").value || 0),
    n_baseline_races: Number($("baselineInput").value || 0),
    historical_strategy_lookback_years: Number($("lookbackInput").value || 0),
    default_overtaking_difficulty: Number($("overtakingInput").value || 55) / 100,
    output_dir: $("outputInput").value || "outputs",
    save_prediction_snapshot: $("snapshotInput").checked,
    save_report_images: $("imagesInput").checked,
    save_raw_results: $("rawInput").checked,
    post_to_discord: false,
    use_weather_forecast: $("forecastInput").checked,
    use_race_control_context: $("raceControlInput").checked,
    use_track_red_flag_base_chance: $("trackFlagInput").checked,
    use_historical_model_calibration: $("historicalModelInput").checked,
    historical_finish_weight: Number($("historicalFinishWeightInput").value || 0),
    historical_dnf_weight: Number($("historicalDnfWeightInput").value || 0),
  };
}

function writeSettings(settings) {
  state.settings = { ...settings };
  $("yearInput").value = settings.year;
  $("eventInput").value = settings.event;
  $("sessionInput").value = settings.session;
  $("nSimsInput").value = settings.n_sims;
  $("seedInput").value = settings.random_seed;
  $("baselineInput").value = settings.n_baseline_races;
  $("lookbackInput").value = settings.historical_strategy_lookback_years;
  $("overtakingInput").value = Math.round(settings.default_overtaking_difficulty * 100);
  $("outputInput").value = settings.output_dir;
  $("snapshotInput").checked = settings.save_prediction_snapshot;
  $("imagesInput").checked = settings.save_report_images;
  $("rawInput").checked = settings.save_raw_results;
  $("forecastInput").checked = settings.use_weather_forecast;
  $("raceControlInput").checked = settings.use_race_control_context;
  $("trackFlagInput").checked = settings.use_track_red_flag_base_chance;
  $("historicalModelInput").checked = settings.use_historical_model_calibration;
  $("historicalFinishWeightInput").value = settings.historical_finish_weight;
  $("historicalDnfWeightInput").value = settings.historical_dnf_weight;
  updateOvertakingValue();
  updateContext();
}

function updateContext() {
  const settings = readSettings();
  updateOvertakingValue();
  const saved = state.outputs.savedContext;
  const showingSaved = !['setup', 'data', 'settings', 'compare'].includes(state.view) && (state.outputs.summaryTable?.rows || []).length > 0;
  const context = showingSaved ? saved : settings;
  const eventLabel = displayEventName(context?.event);
  $("contextTitle").textContent = eventLabel || 'Select an event';
  $("contextTitle").title = `${context?.year || ''} ${eventLabel || ''}${showingSaved ? ' · saved result' : ' · setup'}`;
  $("metricSession").textContent = context?.session || settings.session;
  $("metricSims").textContent = Number(settings.n_sims).toLocaleString();
  $("metricFiles").textContent = String((state.outputs.files || []).length);
  const weather = state.outputs.weather || {};
  $("metricWeather").textContent = weather.chaos == null ? 'Unknown' : `${Number(weather.chaos).toFixed(1)}%`;
  const health = state.outputs.runHealth || {};
  const different = saved && (saved.year !== settings.year || saved.session !== settings.session || !['latest', saved.event].includes(settings.event));
  $("runHealthMessage").textContent = different ? 'Setup differs from saved results. Run a simulation to apply it.' : (health.message || 'No saved outputs yet.');
  if (typeof updateWorkbenchContext === 'function') updateWorkbenchContext();
}

function sessionModeLabel(mode) {
  if (mode === "pre") {
    return "Pre-FP1 run";
  }
  if (mode === "practice") {
    return "Practice run";
  }
  if (mode === "quali") {
    return "Quali run";
  }
  return "Race run";
}

// Readable headers for the snake_case columns written by the simulation outputs.
const columnLabels = {
  avg_finish: "Avg finish", win_chance: "Win", podium_chance: "Podium", dnf_chance: "DNF",
  points_chance: "Points finish", points_scoring_chance: "Points finish", top5_chance: "Top 5", top10_chance: "Top 10",
  avg_points: "Avg points", avg_grid: "Avg grid", finish_p25: "Finish P25", finish_p75: "Finish P75",
  avg_fantasy_points: "Fantasy pts", fantasy_points: "Fantasy pts", fantasy_ceiling_p90: "Ceiling (P90)",
  fantasy_floor_p10: "Floor (P10)", fantasy_price: "Price", fantasy_xppm: "Pts per $m",
  primary_strategy: "Strategy", alternative_strategy: "Alternative", expected_stops: "Stops",
  strategy_confidence: "Confidence", risk_level: "Risk", primary_score: "Strategy score",
  quali_pace_score: "Quali pace", race_pace_score: "Race pace", long_run_pace_score: "Long-run pace",
  strategy_score: "Strategy score", reliability_score: "Reliability (0–100)", tyre_deg_score: "Tyre deg",
  current_weight: "Session weight", model_uncertainty: "Model uncertainty", performance_uncertainty: "Performance uncertainty",
  engine_reliability_score: "PU reliability (0–100)", team_dnf_rate: "Team DNF", driver_dnf_rate: "Driver DNF",
  quali_rank_from_laps: "Rank", clean_laps: "Clean laps", best_lap: "Best lap (s)", median_lap: "Median lap (s)",
  ideal_lap: "Ideal lap (s)", avg_lap: "Avg lap (s)", gap_to_fastest: "Gap (s)", ideal_gap_to_fastest: "Ideal gap (s)",
  best_s1: "Best S1 (s)", best_s2: "Best S2 (s)", best_s3: "Best S3 (s)", avg_speed_trap: "Speed trap (km/h)",
  laps_in_run: "Run laps", run_start_lap: "From lap", run_end_lap: "To lap", degradation_per_lap: "Deg / lap (s)",
  row_count: "Rows", size_bytes: "Size", modified_at: "Modified", exists: "Saved", GridPosition: "Grid",
};

function columnLabel(column) {
  if (columnLabels[column]) return columnLabels[column];
  if (!/^[a-z0-9]+(_[a-z0-9]+)+$|^[a-z]+$/.test(column)) return column;
  const words = column.split("_").map((word) => (/^(dnf|pu|fia|sc|vsc|p\d+|s\d)$/.test(word) ? word.toUpperCase() : word));
  return words.join(" ").replace(/^./, (c) => c.toUpperCase());
}

function sortValue(value) {
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : String(value).toLowerCase();
}

// Reorders rendered rows by the saved sort, moving the existing <tr> nodes so their listeners survive.
function applyTableSort(target) {
  const sort = state.tableSort?.[target.id];
  const table = target.querySelector("table");
  if (!table) return;
  table.querySelectorAll("th[data-column]").forEach((th) => {
    th.setAttribute("aria-sort", th.dataset.column === sort?.column ? (sort.direction > 0 ? "ascending" : "descending") : "none");
  });
  const body = table.tBodies[0];
  const rows = Array.from(body.rows);
  const index = sort ? Array.from(table.querySelectorAll("th[data-column]")).findIndex((th) => th.dataset.column === sort.column) : -1;
  const key = (row) => (index < 0 ? null : sortValue(row.cells[index]?.dataset.value));
  rows.sort((a, b) => {
    const x = key(a), y = key(b);
    if (index < 0 || x === y) return Number(a.dataset.row) - Number(b.dataset.row);
    if (x == null) return 1;
    if (y == null) return -1;
    if (typeof x !== typeof y) return typeof x === "number" ? -1 : 1;
    return (x < y ? -1 : 1) * sort.direction;
  });
  body.append(...rows);
}

function renderTable(targetId, payload, { sortable = true } = {}) {
  const target = $(targetId);
  const columns = payload?.columns || [];
  const rows = payload?.rows || [];

  if (!columns.length) {
    target.innerHTML = `<div class="empty">No data available yet.</div>`;
    return;
  }

  // A column is numeric when every filled cell parses as a number; those align right.
  const numericColumns = new Set(columns.filter((column) => {
    const values = rows.map((row) => row[column]).filter((value) => value != null && value !== "");
    return values.length > 0 && values.every((value) => Number.isFinite(Number(value)));
  }));
  const cellClass = (column) => (numericColumns.has(column) ? ' class="num"' : "");
  const head = columns.map((column) => {
    const label = escapeHtml(columnLabel(column));
    const title = columnLabel(column) === column ? "" : ` title="${escapeHtml(column)}"`;
    return sortable
      ? `<th${cellClass(column)} data-column="${escapeHtml(column)}" aria-sort="none"${title}><button type="button" class="sort-button">${label}</button></th>`
      : `<th${cellClass(column)}${title}>${label}</th>`;
  }).join("");
  const body = rows
    .map((row, index) => `<tr data-row="${index}">${columns.map((column) => `<td${cellClass(column)} data-value="${escapeHtml(row[column] ?? '')}" title="${escapeHtml(row[column] ?? '')}">${escapeHtml(typeof formatCell === 'function' ? formatCell(column, row[column]) : row[column] ?? "")}</td>`).join("")}</tr>`)
    .join("");
  target.innerHTML = `<table${sortable ? ' class="sortable"' : ""}><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  if (!sortable) return;
  target.querySelectorAll("th[data-column] button").forEach((button) => button.addEventListener("click", () => {
    const column = button.parentElement.dataset.column;
    const current = state.tableSort?.[targetId];
    // Numbers start high-to-low, text A-Z; a third click restores the original order.
    const first = numericColumns.has(column) ? -1 : 1;
    const next = current?.column !== column ? { column, direction: first }
      : current.direction === first ? { column, direction: -first } : null;
    state.tableSort = { ...state.tableSort, [targetId]: next };
    applyTableSort(target);
  }));
  applyTableSort(target);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderBarChart(targetId, points, fill = colors.red, { max = null, unit = "" } = {}) {
  const target = $(targetId);
  const items = points || [];

  if (!items.length) {
    target.innerHTML = `<div class="empty">No chart data yet.</div>`;
    return;
  }

  // A fixed max (e.g. 100 for percentages) keeps bars comparable between charts.
  const maxValue = max ?? Math.max(...items.map((item) => Number(item.value) || 0), 1);
  target.innerHTML = items
    .map((item) => {
      const known = item.value != null && item.value !== "" && Number.isFinite(Number(item.value));
      const value = known ? Number(item.value) : 0;
      const width = known ? Math.min(100, Math.max(2, (value / maxValue) * 100)) : 0;
      return `
        <div class="bar-row">
          <div class="bar-label" title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</div>
          <div class="bar-track"><div class="bar-fill" style="width:${width}%;background:${item.fill || fill}"></div></div>
          <div class="bar-value">${known ? `${value.toFixed(1)}${unit}` : "Unknown"}</div>
        </div>`;
    })
    .join("");
}

// Draws telemetry x/y points as a scalable SVG. colourFor(point) picks each segment's colour.
function trackSvg(points, label, colourFor = () => "var(--text-2)") {
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs), maxY = Math.max(...ys);
  const width = Math.max(Math.max(...xs) - minX, 1), height = Math.max(maxY - Math.min(...ys), 1);
  const pad = Math.max(width, height) * 0.04;
  const paths = [];
  let current = null;
  points.forEach((point, index) => {
    const colour = colourFor(point);
    const xy = `${(point.x - minX).toFixed(1)} ${(maxY - point.y).toFixed(1)}`;
    if (!current || current.colour !== colour) {
      // Start each run at the previous point so the line stays continuous.
      const start = index ? points[index - 1] : point;
      current = { colour, d: `M${(start.x - minX).toFixed(1)} ${(maxY - start.y).toFixed(1)}` };
      paths.push(current);
    }
    current.d += `L${xy}`;
  });
  return `<svg viewBox="${-pad} ${-pad} ${width + pad * 2} ${height + pad * 2}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${escapeHtml(label)}">${paths
    .map((path) => `<path d="${path.d}" stroke="${path.colour}"/>`)
    .join("")}</svg>`;
}

function trackMessage(title, detail = "") {
  return `<div class="track-empty"><strong>${escapeHtml(title)}</strong>${detail ? `<small>${escapeHtml(detail)}</small>` : ""}</div>`;
}

function renderTrack(track) {
  const points = track?.points || [];
  const sectors = track?.sectors || {};
  const fastestLap = track?.fastestLap || {};
  const selectedSession = track?.session || readSettings().session;
  $("trackContext").textContent = `${track?.year || ''} ${track?.event || 'Unknown event'} · ${selectedSession} · ${track?.message || 'No telemetry status recorded.'}`;
  const sectorColour = { S1: colors.red, S2: colors.amber, S3: colors.blue };
  $("trackMap").innerHTML = points.length
    ? trackSvg(points, `${track?.event || 'Circuit'} layout coloured by sector`, (point) =>
        point.sector ? sectorColour[point.sector] || colors.muted : point.progress < 1 / 3 ? colors.red : point.progress < 2 / 3 ? colors.amber : colors.blue)
    : trackMessage(track?.message || `Telemetry status unknown for ${selectedSession}.`);

  const sectorCards = ["S1", "S2", "S3"]
    .map((sector) => {
      const leader = sectors[sector] || {};
      const seconds = leader.seconds ? `${Number(leader.seconds).toFixed(3)}s` : "No time";
      return `<div class="sector-pill"><span>${sector} leader</span><strong>${escapeHtml(leader.driver || "n/a")}</strong><span>${seconds}</span></div>`;
    })
    .join("");
  const fastestSeconds = fastestLap.seconds ? `${Number(fastestLap.seconds).toFixed(3)}s` : "No time";
  const lapText = fastestLap.lap ? `Lap ${escapeHtml(fastestLap.lap)}` : selectedSession;
  $("sectorLegend").innerHTML = `${sectorCards}<div class="sector-pill fastest-lap"><span>Fastest lap</span><strong>${escapeHtml(
    fastestLap.driver || "n/a",
  )}</strong><span>${fastestSeconds} - ${lapText}</span></div>`;
}

function renderWeather(weather) {
  renderBarChart("weatherChart", [
    { label: "Forecast rain", value: weather?.rain, fill: colors.blue },
    { label: "Simulated red flag", value: weather?.chaos, fill: colors.red },
    { label: "Mean driver DNF", value: weather?.dnf, fill: colors.orange },
  ], colors.blue, { max: 100, unit: "%" });
  $("weatherChartSource").textContent = weather?.source || "No weather source available";
}

function renderOutputs(outputs) {
  state.outputs = outputs || {};
  const health = state.outputs.runHealth || {};
  const rows = [
    {check:'Saved context', value:`${health.context?.year || ''} ${health.context?.event || 'Unknown'} ${health.context?.session || ''}`, detail:health.context_source || 'not recorded'},
    {check:'Session completion',value:health.completion || 'not recorded',detail:'From loaded FastF1 session status; lap presence alone does not prove completion.'},
    {check:'Session selection',value:health.selection_reason || 'not recorded',detail:health.selection_policy || 'No saved automatic selection policy'},
    {check:'Grid assumptions',value:(health.grid_sources || []).join(', ') || 'not recorded',detail:'Estimated model grids are assumptions, not confirmed starting positions.'},
    {check:'Driver coverage',value:`${health.matched_drivers || 0}/${health.drivers_in_laps || 0} lap drivers matched`,detail:`${health.drivers_in_model || 0} model drivers; ${health.duplicate_model_drivers || 0} duplicate IDs; missing: ${(health.missing_model_drivers || []).join(', ') || 'none'}`},
    {check:'Session laps',value:health.lap_rows ?? 'unknown',detail:`${health.clean_laps ?? 'unknown'} clean push laps`},
    {check:'Telemetry',value:health.telemetry_status || 'unknown',detail:health.telemetry_message || 'not checked'},
    {check:'Saved-data age',value:health.output_age_hours == null ? 'unknown' : `${health.output_age_hours} hours`,detail:health.saved_at_utc ? `Lap export saved ${health.saved_at_utc}; file age, not an upstream freshness guarantee.` : 'No saved lap timestamp.'},
  ];
  renderTable('runHealthTable',{columns:['check','value','detail'],rows});
  const charts = state.outputs.resultsCharts || {};
  const screens = state.outputs.sessionScreens || {};
  renderBarChart("dnfChart", charts.dnf, colors.orange, { unit: "%" });
  renderBarChart("fantasyChart", charts.fantasy, colors.blue);
  renderTable("summaryTable", state.outputs.summaryTable);
  $("practiceModeBadge").textContent = sessionModeLabel(state.outputs.sessionMode);
  $("qualiModeBadge").textContent = sessionModeLabel(state.outputs.sessionMode);
  renderTable("practiceSectorTable", screens.practice?.sectors);
  renderTable("practicePaceTable", screens.practice?.pace);
  renderTable("practiceLongRunTable", screens.practice?.longRun);
  renderTable("qualiSectorTable", screens.quali?.sectors);
  renderTable("qualiPaceTable", screens.quali?.pace);
  renderTable("signalOverviewTable", state.outputs.signals?.overview);
  renderTable("driverSignalsTable", state.outputs.signals?.drivers);
  $("modelCommentary").textContent = state.outputs.signals?.commentary || "No model commentary found yet.";
  renderTrack(displayedTrack());
  renderWeather(state.outputs.weather);
  renderBarChart("engineChart", state.outputs.reliability?.engineChart, colors.green, { max: 100 });
  renderTable("reliabilityTable", state.outputs.reliability?.table);
  renderTable("strategyTable", state.outputs.strategy);
  TyreStrategy.render(state.outputs);
  renderTable("raceOverviewTable", state.outputs.raceReview?.overview);
  renderBarChart("outlierChart", state.outputs.raceReview?.outlierChart, colors.red);
  renderTable("actualStrategyTable", state.outputs.raceReview?.strategy);
  renderTable("outlierTable", state.outputs.raceReview?.outliers);
  renderTable("dataHealthTable", { columns: ["label", "status", "row_count", "message", "path"], rows: state.outputs.dataHealth || [] });
  renderTable("filesTable", { columns: ["label", "exists", "size_bytes", "path"], rows: state.outputs.files || [] });
  if (typeof renderWorkbench === 'function') renderWorkbench();
  updateContext();
}

async function refreshOutputs() {
  const outputs = await api().outputs({...readSettings(), output_dir: state.activeOutputDir || readSettings().output_dir});
  renderOutputs(outputs);
}

async function startRun() {
  await setPcFollowing(false);
  const response = await api().start_run({ ...readSettings(), candidates: readCandidates() });
  if (!response.ok) {
    $("runLog").textContent = response.message;
    return;
  }
  state.activeOutputDir = response.outputDir;
  state.manualRunning = true;
  $("runButton").disabled = true;
  await pollRunStatus();
}

async function pollRunStatus() {
  const status = await api().run_status();
  state.manualRunning = Boolean(status.running);
  $("runDot").classList.toggle("running", Boolean(status.running));
  $("runState").textContent = status.running ? "Running" : status.exitCode === 0 ? "Run complete" : status.exitCode ? "Run failed" : "Ready";
  // The log scrolls to its end, so the plain-language reason goes last.
  const failure = !status.running && status.exitCode && status.error ? `\n\nRun failed: ${status.error}` : "";
  $("runLog").textContent = (status.log || "No run output yet.") + failure;
  $("runLog").scrollTop = $("runLog").scrollHeight;
  $("runButton").disabled = Boolean(status.running);

  if (status.running) {
    clearTimeout(state.statusTimer);
    state.statusTimer = setTimeout(() => safeAction(pollRunStatus), 1200);
  } else if (status.exitCode === 0) {
    await refreshOutputs();
  }
}

function setupNavigation() {
  document.querySelectorAll("button.nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      navigate(button.dataset.view);
    });
  });
}

function setupEvents() {
  $("yearInput").addEventListener("change", () => safeAction(async () => {
    const year = Number($("yearInput").value);
    $("eventInput").disabled=true;
    state.setupTrack={status:'loading',points:[],message:'Loading the selected season calendar…'};
    drawSetupTrack(state.setupOptions?.trackProfile || {});
    try {
      const events = await api().events_for_year(year);
      if(Number($("yearInput").value) !== year)return;
      setOptions($("eventInput"), events, events.includes(state.settings.event) ? state.settings.event : "latest");
      await refreshSetupOptions(readSettings().session);
    } finally {
      if(Number($("yearInput").value)===year)$("eventInput").disabled=false;
    }
  }));

  $("eventInput").addEventListener("change", () => safeAction(() => refreshSetupOptions(readSettings().session)));

  ["sessionInput", "nSimsInput", "outputInput"].forEach((id) => {
    $(id).addEventListener("change", updateContext);
  });
  $("overtakingInput").addEventListener("input", updateContext);
  $("overtakingInput").addEventListener("change", updateContext);

  $("refreshButton").addEventListener("click", () => safeAction(refreshOutputs));
  $("runButton").addEventListener("click", () => safeAction(startRun));
  $("openOutputButton").addEventListener("click", () => safeAction(() => api().open_output_dir(state.outputs.outputDir || readSettings().output_dir)));
}

async function boot() {
  if (state.booted) return;
  state.booted = true;
  initSetupControls();
  setupNavigation();
  setupEvents();
  initWorkbench();
  const initial = await api().initial_state();
  state.initial = initial;
  state.reference = initial.modelReference;
  state.projectDefaults = initial.projectDefaults;
  state.activeOutputDir = initial.outputs?.outputDir;
  setOptions($("yearInput"), initial.seasons, initial.settings.year);
  setOptions($("eventInput"), initial.events, initial.settings.event);
  writeSettings(initial.settings);
  renderCandidateOptions(initial.modelCandidates);
  applySetupOptions(initial.setupOptions || { sessions: initial.sessions }, initial.settings.session);
  renderOutputs(initial.outputs);
  await loadDataPreview();
  applyPreferences(initial.preferences || {});
  initPcRuns(initial);
  initHistoricalLibrary();
  initReplay();
  initModelTraining();
  await refreshSetupTrack();
}
