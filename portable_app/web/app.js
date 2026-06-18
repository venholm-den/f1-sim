const state = {
  settings: {},
  outputs: {},
  statusTimer: null,
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

function readSettings() {
  return {
    year: Number($("yearInput").value),
    event: $("eventInput").value || "latest",
    session: $("sessionInput").value || "Q",
    n_sims: Number($("nSimsInput").value || 1),
    random_seed: Number($("seedInput").value || 0),
    n_baseline_races: Number($("baselineInput").value || 0),
    historical_strategy_lookback_years: Number($("lookbackInput").value || 0),
    default_overtaking_difficulty: Number($("overtakingInput").value || 55) / 100,
    output_dir: $("outputInput").value || "outputs",
    save_prediction_snapshot: true,
    save_report_images: true,
    save_raw_results: true,
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
  $("forecastInput").checked = settings.use_weather_forecast;
  $("raceControlInput").checked = settings.use_race_control_context;
  $("trackFlagInput").checked = settings.use_track_red_flag_base_chance;
  $("historicalModelInput").checked = settings.use_historical_model_calibration;
  $("historicalFinishWeightInput").value = settings.historical_finish_weight;
  $("historicalDnfWeightInput").value = settings.historical_dnf_weight;
  updateContext();
}

function updateContext() {
  const settings = readSettings();
  $("contextTitle").textContent = `${settings.year} ${settings.event} - ${settings.session}`;
  $("metricSession").textContent = settings.session;
  $("metricSims").textContent = Number(settings.n_sims).toLocaleString();
  $("metricFiles").textContent = String((state.outputs.files || []).length);
  const weather = state.outputs.weather || {};
  $("metricWeather").textContent = `${Math.round(weather.chaos || 0)}% chaos`;
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
    .map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(row[column] ?? "")}</td>`).join("")}</tr>`)
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
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#090d14";
  context.fillRect(0, 0, canvas.width, canvas.height);

  if (!points.length) {
    context.fillStyle = colors.muted;
    context.font = "18px Segoe UI";
    context.fillText("Real track telemetry is not available yet for this event/session.", 32, 58);
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

    const scale = (point) => ({
      x: pad + ((point.x - minX) / spanX) * drawW,
      y: pad + ((maxY - point.y) / spanY) * drawH,
    });

    for (let index = 0; index < points.length - 1; index += 1) {
      const start = points[index];
      const end = points[index + 1];
      const p1 = scale(start);
      const p2 = scale(end);
      const sectorColor = start.progress < 1 / 3 ? colors.red : start.progress < 2 / 3 ? colors.amber : colors.blue;
      context.strokeStyle = sectorColor;
      context.lineWidth = 7;
      context.lineCap = "round";
      context.beginPath();
      context.moveTo(p1.x, p1.y);
      context.lineTo(p2.x, p2.y);
      context.stroke();
    }
  }

  $("sectorLegend").innerHTML = ["S1", "S2", "S3"]
    .map((sector) => {
      const leader = sectors[sector] || {};
      const seconds = leader.seconds ? `${Number(leader.seconds).toFixed(3)}s` : "No time";
      return `<div class="sector-pill"><span>${sector} leader</span><strong>${escapeHtml(leader.driver || "n/a")}</strong><span>${seconds}</span></div>`;
    })
    .join("");
}

function renderWeather(weather) {
  const canvas = $("weatherCanvas");
  const context = canvas.getContext("2d");
  const rows = [
    ["Rain/Wet", weather?.rain || 0, colors.blue],
    ["Chaos/red flag", weather?.chaos || 0, colors.red],
    ["DNF pressure", weather?.dnf || 0, "#f97316"],
    ["Tyre degradation", weather?.degradation || 0, colors.amber],
    ["Uncertainty", weather?.uncertainty || 0, "#818cf8"],
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
    context.fillText(`${Math.round(value)}%`, 642, y);
  });

  context.fillStyle = colors.muted;
  context.font = "13px Segoe UI";
  context.fillText(String(weather?.source || "No weather source available").slice(0, 105), 28, canvas.height - 28);
}

function renderOutputs(outputs) {
  state.outputs = outputs || {};
  const charts = state.outputs.resultsCharts || {};
  renderBarChart("winChart", charts.win, colors.red);
  renderBarChart("podiumChart", charts.podium, colors.amber);
  renderBarChart("dnfChart", charts.dnf, "#f97316");
  renderBarChart("fantasyChart", charts.fantasy, colors.blue);
  renderTable("summaryTable", state.outputs.summaryTable);
  renderTable("signalOverviewTable", state.outputs.signals?.overview);
  renderTable("driverSignalsTable", state.outputs.signals?.drivers);
  $("modelCommentary").textContent = state.outputs.signals?.commentary || "No model commentary found yet.";
  renderTrack(state.outputs.track);
  renderWeather(state.outputs.weather);
  renderBarChart("engineChart", state.outputs.reliability?.engineChart, colors.green);
  renderTable("reliabilityTable", state.outputs.reliability?.table);
  renderTable("strategyTable", state.outputs.strategy);
  renderTable("raceOverviewTable", state.outputs.raceReview?.overview);
  renderBarChart("outlierChart", state.outputs.raceReview?.outlierChart, colors.red);
  renderTable("actualStrategyTable", state.outputs.raceReview?.strategy);
  renderTable("outlierTable", state.outputs.raceReview?.outliers);
  renderTable("dataHealthTable", { columns: ["label", "status", "row_count", "message", "path"], rows: state.outputs.dataHealth || [] });
  renderTable("filesTable", { columns: ["label", "exists", "size_bytes", "path"], rows: state.outputs.files || [] });
  updateContext();
}

async function refreshOutputs() {
  const outputs = await api().outputs(readSettings());
  renderOutputs(outputs);
}

async function startRun() {
  const response = await api().start_run(readSettings());
  if (!response.ok) {
    $("runLog").textContent = response.message;
    return;
  }
  pollRunStatus();
}

async function pollRunStatus() {
  const status = await api().run_status();
  $("runDot").classList.toggle("running", Boolean(status.running));
  $("runState").textContent = status.running ? "Running" : status.exitCode === 0 ? "Run complete" : status.exitCode ? "Run failed" : "Ready";
  $("runLog").textContent = status.log || "No run output yet.";
  $("runLog").scrollTop = $("runLog").scrollHeight;

  if (status.running) {
    clearTimeout(state.statusTimer);
    state.statusTimer = setTimeout(pollRunStatus, 1200);
  } else if (status.exitCode === 0) {
    await refreshOutputs();
  }
}

function setupNavigation() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
      button.classList.add("active");
      $(`view-${button.dataset.view}`).classList.add("active");
    });
  });
}

function setupEvents() {
  $("yearInput").addEventListener("change", async () => {
    const events = await api().events_for_year(Number($("yearInput").value));
    setOptions($("eventInput"), events, events.includes(state.settings.event) ? state.settings.event : "latest");
    updateContext();
  });

  ["eventInput", "sessionInput", "nSimsInput", "outputInput"].forEach((id) => {
    $(id).addEventListener("change", updateContext);
  });

  $("refreshButton").addEventListener("click", refreshOutputs);
  $("runButton").addEventListener("click", startRun);
  $("openOutputButton").addEventListener("click", () => api().open_output_dir(readSettings().output_dir));
}

async function boot() {
  setupNavigation();
  setupEvents();
  const initial = await api().initial_state();
  setOptions($("yearInput"), initial.seasons, initial.settings.year);
  setOptions($("eventInput"), initial.events, initial.settings.event);
  setOptions($("sessionInput"), initial.sessions, initial.settings.session);
  writeSettings(initial.settings);
  renderOutputs(initial.outputs);
}

window.addEventListener("pywebviewready", boot);
