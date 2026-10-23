const state = {
  settings: {},
  outputs: {},
  statusTimer: null,
  view: 'setup',
  activeOutputDir: null,
};

const colors = {
  red: "#ef233c",
  amber: "#f59e0b",
  blue: "#38bdf8",
  green: "#22c55e",
  muted: "#8ea0b8",
  panel: "#101620",
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
  if (typeof renderSessionPills === 'function') renderSessionPills();
  const overtakingDifficulty = Number(trackProfile.overtaking_difficulty);
  if (Number.isFinite(overtakingDifficulty)) {
    setOvertakingPercent(overtakingDifficulty * 100);
  }
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
  const eventLabel = context?.event === 'latest' ? state.setupOptions?.trackProfile?.event || 'Latest eligible event' : context?.event;
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

function renderTable(targetId, payload) {
  const target = $(targetId);
  const columns = payload?.columns || [];
  const rows = payload?.rows || [];

  if (!columns.length) {
    target.innerHTML = `<div class="empty">No data available yet.</div>`;
    return;
  }

  const head = columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("");
  const body = rows
    .map((row) => `<tr>${columns.map((column) => `<td title="${escapeHtml(row[column] ?? '')}">${escapeHtml(typeof formatCell === 'function' ? formatCell(column, row[column]) : row[column] ?? "")}</td>`).join("")}</tr>`)
    .join("");
  target.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderBarChart(targetId, points, fill = colors.red) {
  const target = $(targetId);
  const items = points || [];

  if (!items.length) {
    target.innerHTML = `<div class="empty">No chart data yet.</div>`;
    return;
  }

  const maxValue = Math.max(...items.map((item) => Number(item.value) || 0), 1);
  target.innerHTML = items
    .map((item) => {
      const value = Number(item.value) || 0;
      const width = Math.max(2, (value / maxValue) * 100);
      return `
        <div class="bar-row">
          <div class="bar-label" title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</div>
          <div class="bar-track"><div class="bar-fill" style="width:${width}%;background:${fill}"></div></div>
          <div class="bar-value">${value.toFixed(1)}</div>
        </div>`;
    })
    .join("");
}

function renderTrack(track) {
  const canvas = $("trackCanvas");
  const context = canvas.getContext("2d");
  const points = track?.points || [];
  const sectors = track?.sectors || {};
  const fastestLap = track?.fastestLap || {};
  const selectedSession = track?.session || readSettings().session;
  $("trackContext").textContent = `${track?.year || ''} ${track?.event || 'Unknown event'} · ${selectedSession} · ${track?.message || 'No telemetry status recorded.'}`;
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#090d14";
  context.fillRect(0, 0, canvas.width, canvas.height);

  if (!points.length) {
    context.fillStyle = colors.muted;
    context.font = "18px Segoe UI";
    context.font = "14px Segoe UI";
    context.fillText(track?.message || `Telemetry status unknown for ${selectedSession}.`, 24, 58);
  } else {
    const xs = points.map((point) => point.x);
    const ys = points.map((point) => point.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const spanX = Math.max(maxX - minX, 1);
    const spanY = Math.max(maxY - minY, 1);
    const pad = 52;
    const drawW = canvas.width - pad * 2;
    const drawH = canvas.height - pad * 2;
    const factor = Math.min(drawW/spanX, drawH/spanY);
    const offsetX = (canvas.width-spanX*factor)/2, offsetY = (canvas.height-spanY*factor)/2;

    const scale = (point) => ({
      x: offsetX + (point.x-minX)*factor,
      y: offsetY + (maxY-point.y)*factor,
    });

    for (let index = 0; index < points.length - 1; index += 1) {
      const start = points[index];
      const end = points[index + 1];
      const p1 = scale(start);
      const p2 = scale(end);
      const sectorColor = start.sector ? ({S1:colors.red,S2:colors.amber,S3:colors.blue}[start.sector] || colors.muted) :
        start.progress < 1 / 3 ? colors.red : start.progress < 2 / 3 ? colors.amber : colors.blue;
      context.strokeStyle = sectorColor;
      context.lineWidth = 7;
      context.lineCap = "round";
      context.beginPath();
      context.moveTo(p1.x, p1.y);
      context.lineTo(p2.x, p2.y);
      context.stroke();
    }
  }

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
  const canvas = $("weatherCanvas");
  const context = canvas.getContext("2d");
  const rows = [
    ["Forecast rain", weather?.rain, colors.blue],
    ["Simulated red flag", weather?.chaos, colors.red],
    ["Mean driver DNF", weather?.dnf, "#f97316"],
  ];

  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#090d14";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.font = "16px Segoe UI";

  rows.forEach(([label, rawValue, color], index) => {
    const value = Math.max(0, Math.min(100, Number(rawValue) || 0));
    const y = 58 + index * 58;
    context.fillStyle = "#cbd5e1";
    context.fillText(label, 28, y);
    context.fillStyle = "#1f2937";
    context.fillRect(190, y - 18, 430, 18);
    context.fillStyle = color;
    context.fillRect(190, y - 18, 430 * (value / 100), 18);
    context.fillStyle = "#edf3fb";
    context.fillText(rawValue == null ? 'Unknown' : `${value.toFixed(1)}%`, 642, y);
  });

  context.fillStyle = colors.muted;
  context.font = "13px Segoe UI";
  context.fillText(String(weather?.source || "No weather source available").slice(0, 105), 28, canvas.height - 28);
  const observed = weather?.observed || {}, modifiers = weather?.modifiers || {};
  const number = value => value == null ? 'not recorded' : Number(value).toFixed(2);
  $("weatherDetails").textContent = `Saved observations — air: ${number(observed.air_temp_avg)} °C; track: ${number(observed.track_temp_avg)} °C; rainfall: ${observed.rainfall_flag == null ? 'not recorded' : observed.rainfall_flag ? 'observed' : 'not observed'}. Model weather multipliers — disruption: ${number(modifiers.chaos_factor)}; DNF: ${number(modifiers.dnf_factor)}; degradation: ${number(modifiers.degradation_factor)}. Spread/degradation scores are not probabilities.`;
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
  renderBarChart("winChart", charts.win, colors.red);
  renderBarChart("podiumChart", charts.podium, colors.amber);
  renderBarChart("dnfChart", charts.dnf, "#f97316");
  renderBarChart("fantasyChart", charts.fantasy, colors.blue);
  renderTable("summaryTable", state.outputs.summaryTable);
  $("practiceModeBadge").textContent = sessionModeLabel(state.outputs.sessionMode);
  $("qualiModeBadge").textContent = sessionModeLabel(state.outputs.sessionMode);
  $("raceModeBadge").textContent = sessionModeLabel(state.outputs.sessionMode);
  renderTable("practiceSectorTable", screens.practice?.sectors);
  renderTable("practicePaceTable", screens.practice?.pace);
  renderTable("practiceLongRunTable", screens.practice?.longRun);
  renderTable("qualiSectorTable", screens.quali?.sectors);
  renderTable("qualiPaceTable", screens.quali?.pace);
  renderTable("raceScreenSummaryTable", screens.race?.summary);
  renderTable("raceScreenStrategyTable", screens.race?.strategy);
  renderTable("signalOverviewTable", state.outputs.signals?.overview);
  renderTable("driverSignalsTable", state.outputs.signals?.drivers);
  $("modelCommentary").textContent = state.outputs.signals?.commentary || "No model commentary found yet.";
  renderTrack(displayedTrack());
  renderWeather(state.outputs.weather);
  renderBarChart("engineChart", state.outputs.reliability?.engineChart, colors.green);
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
  const response = await api().start_run(readSettings());
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
  $("runLog").textContent = status.log || "No run output yet.";
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
  initRedesign();
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
  applySetupOptions(initial.setupOptions || { sessions: initial.sessions }, initial.settings.session);
  renderOutputs(initial.outputs);
  await loadDataPreview();
  applyPreferences(initial.preferences || {});
  initPcRuns(initial);
  initHistoricalLibrary();
  initModelTraining();
  await refreshSetupTrack();
}
