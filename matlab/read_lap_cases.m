function cases = read_lap_cases(inputCsv)
%READ_LAP_CASES Validate inputs before any simulations are started.
options = detectImportOptions(inputCsv, 'VariableNamingRule', 'preserve');
numericNames = ["race_laps", "base_lap_time_seconds", "pace_offset_seconds", ...
    "tyre_degradation_seconds_per_lap", "initial_tyre_age_laps", ...
    "initial_fuel_penalty_seconds", "fuel_gain_per_lap_seconds", "pit_loss_seconds"];
required = ["Driver", "Team", "pit_laps", numericNames];
missing = setdiff(required, string(options.VariableNames));
if ~isempty(missing)
    error('f1sim:InvalidInputContract', 'Missing columns: %s', strjoin(missing, ', '));
end
textNames = intersect(["Driver", "Team", "pit_laps", "case_id", "scenario"], ...
    string(options.VariableNames));
options = setvartype(options, textNames, 'string');
options = setvartype(options, numericNames, 'double');
if ismember('expected_stops', options.VariableNames)
    options = setvartype(options, 'expected_stops', 'double');
end
cases = readtable(inputCsv, options);
if isempty(cases)
    error('f1sim:InvalidInputContract', 'No cases supplied.');
end
values = cases{:, numericNames};
if any(~isfinite(values), 'all')
    error('f1sim:InvalidInputContract', 'All numeric model inputs must be finite.');
end
nonnegative = ["tyre_degradation_seconds_per_lap", "initial_tyre_age_laps", ...
    "initial_fuel_penalty_seconds", "fuel_gain_per_lap_seconds", "pit_loss_seconds"];
if any(cases{:, nonnegative} < 0, 'all') || ...
        any(cases.base_lap_time_seconds + cases.pace_offset_seconds <= 0)
    error('f1sim:InvalidInputContract', 'Penalties and ages must be nonnegative; lap pace must be positive.');
end
if any(cases.race_laps < 1 | cases.race_laps > 100 | mod(cases.race_laps, 1) ~= 0) ...
        || numel(unique(cases.race_laps)) ~= 1
    error('f1sim:InvalidInputContract', 'Cases must share one integer race distance from 1 to 100.');
end
if any(ismissing(cases.Driver) | strlength(strtrim(cases.Driver)) == 0)
    error('f1sim:InvalidInputContract', 'Driver identifiers must be non-empty.');
end
if ~ismember('scenario', cases.Properties.VariableNames)
    cases.scenario = repmat("baseline", height(cases), 1);
end
if ~ismember('case_id', cases.Properties.VariableNames)
    cases.case_id = cases.Driver + "__" + cases.scenario;
end
if any(ismissing(cases.case_id) | strlength(strtrim(cases.case_id)) == 0) ...
        || numel(unique(cases.case_id)) ~= height(cases) ...
        || any(ismissing(cases.scenario) | strlength(strtrim(cases.scenario)) == 0) ...
        || height(unique(cases(:, {'Driver', 'scenario'}))) ~= height(cases)
    error('f1sim:InvalidInputContract', 'Case IDs and driver/scenario pairs must be unique and non-empty.');
end
for index = 1:height(cases)
    schedule = cases.pit_laps(index);
    laps = [];
    if ~ismissing(schedule) && strlength(strtrim(schedule)) > 0
        laps = str2double(split(schedule, ';'));
    end
    if any(~isfinite(laps) | mod(laps, 1) ~= 0 | laps < 1 | laps >= cases.race_laps(index)) ...
            || any(diff(laps) <= 0)
        error('f1sim:InvalidInputContract', 'Invalid pit schedule for %s: %s', cases.case_id(index), schedule);
    end
    if ismember('expected_stops', cases.Properties.VariableNames) && ...
            (~isfinite(cases.expected_stops(index)) || cases.expected_stops(index) ~= numel(laps))
        error('f1sim:InvalidInputContract', 'Stop count disagrees with schedule for %s.', cases.case_id(index));
    end
end
end
