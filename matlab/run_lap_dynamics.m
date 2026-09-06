function [detailPath, summaryPath, figurePath] = run_lap_dynamics(inputCsv, outputDir)
%RUN_LAP_DYNAMICS Simulate each exported driver using the lap dynamics model.

arguments
    inputCsv (1,1) string = fullfile(repoRoot(), "outputs", "matlab", "lap_dynamics_inputs.csv")
    outputDir (1,1) string = fullfile(repoRoot(), "outputs", "matlab")
end

if ~isfile(inputCsv)
    error("f1sim:InputNotFound", ...
        "Simulink input CSV not found: %s. Run scripts/export_simulink_inputs.py first.", ...
        inputCsv);
end
if ~isfolder(outputDir)
    mkdir(outputDir);
end

matlabDir = fileparts(mfilename("fullpath"));
modelDir = fullfile(matlabDir, "models");
modelName = "f1_lap_dynamics_model";
modelPath = fullfile(modelDir, modelName + ".slx");
addpath(modelDir);

if ~isfile(modelPath)
    build_lap_dynamics_model(modelDir);
end

importOptions = detectImportOptions(inputCsv, "VariableNamingRule", "preserve");
importOptions = setvartype(importOptions, ["Driver", "Team", "pit_laps"], "string");
cases = readtable(inputCsv, importOptions);
validateInputTable(cases);

caseCount = height(cases);
simulationInputs = repmat(Simulink.SimulationInput(modelName), caseCount, 1);

for caseIndex = 1:caseCount
    lapCount = round(cases.race_laps(caseIndex));
    time = (0:lapCount-1)';
    pitStop = zeros(lapCount, 1);
    pitLaps = parsePitLaps(cases.pit_laps(caseIndex), lapCount);
    pitStop(pitLaps) = 1;

    pitSignal = timeseries(pitStop, time);
    pitSignal.Name = "pit_stop";
    externalInputs = Simulink.SimulationData.Dataset;
    externalInputs{1} = pitSignal;

    simulationInputs(caseIndex) = simulationInputs(caseIndex) ...
        .setExternalInput(externalInputs) ...
        .setVariable("base_lap_time_seconds", cases.base_lap_time_seconds(caseIndex)) ...
        .setVariable("pace_offset_seconds", cases.pace_offset_seconds(caseIndex)) ...
        .setVariable("tyre_degradation_seconds_per_lap", cases.tyre_degradation_seconds_per_lap(caseIndex)) ...
        .setVariable("initial_tyre_age_laps", cases.initial_tyre_age_laps(caseIndex)) ...
        .setVariable("initial_fuel_penalty_seconds", cases.initial_fuel_penalty_seconds(caseIndex)) ...
        .setVariable("fuel_gain_per_lap_seconds", cases.fuel_gain_per_lap_seconds(caseIndex)) ...
        .setVariable("pit_loss_seconds", cases.pit_loss_seconds(caseIndex)) ...
        .setModelParameter( ...
            "StopTime", string(lapCount - 1), ...
            "SolverType", "Fixed-step", ...
            "Solver", "FixedStepDiscrete", ...
            "FixedStep", "1", ...
            "SignalLogging", "on", ...
            "SignalLoggingName", "logsout");
end

simulationOutputs = sim(simulationInputs);

detail = table;
summary = table;
for caseIndex = 1:caseCount
    logs = simulationOutputs(caseIndex).logsout;
    lapTime = loggedData(logs, "lap_time");
    cumulativeTime = loggedData(logs, "cumulative_time");
    tyreAge = loggedData(logs, "tyre_age");
    fuelPenalty = loggedData(logs, "fuel_penalty");
    pitPenalty = loggedData(logs, "pit_penalty");
    sampleCount = numel(lapTime);

    driverDetail = table( ...
        repmat(cases.Driver(caseIndex), sampleCount, 1), ...
        repmat(cases.Team(caseIndex), sampleCount, 1), ...
        (1:sampleCount)', ...
        lapTime, cumulativeTime, tyreAge, fuelPenalty, pitPenalty, ...
        'VariableNames', {'Driver', 'Team', 'lap', 'lap_time_seconds', ...
        'cumulative_time_seconds', 'tyre_age_laps', 'fuel_penalty_seconds', ...
        'pit_penalty_seconds'});
    detail = [detail; driverDetail]; %#ok<AGROW>

    driverSummary = table( ...
        cases.Driver(caseIndex), cases.Team(caseIndex), sampleCount, ...
        cumulativeTime(end), mean(lapTime), min(lapTime), max(lapTime), ...
        sum(pitPenalty > 0), ...
        'VariableNames', {'Driver', 'Team', 'race_laps', ...
        'simulated_race_time_seconds', 'mean_lap_time_seconds', ...
        'fastest_lap_time_seconds', 'slowest_lap_time_seconds', 'pit_stops'});
    summary = [summary; driverSummary]; %#ok<AGROW>
end

summary = sortrows(summary, "simulated_race_time_seconds");
summary.simulated_rank = (1:height(summary))';

detailPath = fullfile(outputDir, "lap_dynamics_results.csv");
summaryPath = fullfile(outputDir, "lap_dynamics_summary.csv");
figurePath = fullfile(outputDir, "lap_dynamics.png");
writetable(detail, detailPath);
writetable(summary, summaryPath);
plotResults(detail, figurePath);

fprintf("Wrote lap detail: %s\n", detailPath);
fprintf("Wrote race summary: %s\n", summaryPath);
fprintf("Wrote lap dynamics figure: %s\n", figurePath);
end


function values = loggedData(logs, signalName)
signal = logs.get(signalName).Values;
values = signal.Data(:);
end


function pitLaps = parsePitLaps(value, lapCount)
if iscell(value)
    value = value{1};
end
if any(ismissing(value))
    pitLaps = zeros(0, 1);
    return;
end

textValue = string(value);
if strlength(strtrim(textValue)) == 0
    pitLaps = zeros(0, 1);
    return;
end

parts = split(textValue, ";");
pitLaps = round(str2double(parts));
pitLaps = unique(pitLaps(isfinite(pitLaps) & pitLaps >= 1 & pitLaps <= lapCount));
end


function validateInputTable(cases)
required = ["Driver", "Team", "race_laps", "base_lap_time_seconds", ...
    "pace_offset_seconds", "tyre_degradation_seconds_per_lap", ...
    "initial_tyre_age_laps", "initial_fuel_penalty_seconds", ...
    "fuel_gain_per_lap_seconds", "pit_laps", "pit_loss_seconds"];
missing = setdiff(required, string(cases.Properties.VariableNames));
if ~isempty(missing)
    error("f1sim:InvalidInputContract", ...
        "Simulink input CSV is missing columns: %s", strjoin(missing, ", "));
end
if isempty(cases)
    error("f1sim:InvalidInputContract", "Simulink input CSV contains no driver rows.");
end
if any(cases.race_laps < 1 | cases.race_laps > 100)
    error("f1sim:InvalidInputContract", "race_laps must be between 1 and 100.");
end
end


function plotResults(detail, figurePath)
background = [0.035 0.055 0.09];
foreground = [0.88 0.91 0.95];
figureHandle = figure("Visible", "off", "Color", background, "Position", [100 100 1200 650]);
cleanup = onCleanup(@()close(figureHandle));
axesHandle = axes(figureHandle, "Color", background, "XColor", foreground, ...
    "YColor", foreground, "GridColor", [0.45 0.50 0.58], "GridAlpha", 0.30);
hold(axesHandle, "on");
drivers = unique(detail.Driver, "stable");
finalTimes = zeros(numel(drivers), 1);
for index = 1:numel(drivers)
    driverRows = detail.Driver == drivers(index);
    cumulative = detail.cumulative_time_seconds(driverRows);
    finalTimes(index) = cumulative(end);
end
[~, order] = sort(finalTimes);
drivers = drivers(order(1:min(10, numel(order))));
colours = lines(numel(drivers));
for index = 1:numel(drivers)
    rows = detail.Driver == drivers(index);
    plot(axesHandle, detail.lap(rows), detail.lap_time_seconds(rows), ...
        "LineWidth", 1.6, "Color", colours(index, :), "DisplayName", drivers(index));
end
grid(axesHandle, "on");
xlabel(axesHandle, "Lap");
ylabel(axesHandle, "Simulated lap time (s)");
title(axesHandle, "F1 Simulink lap dynamics - top 10 simulated finishers");
legendHandle = legend(axesHandle, "Location", "eastoutside");
legendHandle.Color = background;
legendHandle.TextColor = foreground;
legendHandle.EdgeColor = [0.30 0.34 0.42];
exportgraphics(figureHandle, figurePath, "Resolution", 150);
clear cleanup;
end


function root = repoRoot()
root = fileparts(fileparts(mfilename("fullpath")));
end
