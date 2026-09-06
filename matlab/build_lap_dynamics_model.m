function modelPath = build_lap_dynamics_model(outputDir)
%BUILD_LAP_DYNAMICS_MODEL Build the versioned F1 lap-dynamics Simulink model.
%
% The model runs at one discrete sample per race lap. Runtime parameters are
% supplied with Simulink.SimulationInput by run_lap_dynamics.m.

arguments
    outputDir (1,1) string = fullfile(fileparts(mfilename('fullpath')), "models")
end

modelName = "f1_lap_dynamics_model";
if ~isfolder(outputDir)
    mkdir(outputDir);
end
modelPath = fullfile(outputDir, modelName + ".slx");

if bdIsLoaded(modelName)
    if strcmp(get_param(modelName, 'Dirty'), 'on')
        error('f1sim:UnsavedModel', 'Save or close the edited model before rebuilding.');
    end
    close_system(modelName, 0);
end

new_system(modelName);
cleanup = onCleanup(@()closeIfLoaded(modelName));

set_param(modelName, ...
    "SolverType", "Fixed-step", ...
    "Solver", "FixedStepDiscrete", ...
    "FixedStep", "1", ...
    "StartTime", "0", ...
    "StopTime", "56", ...
    "SignalLogging", "on", ...
    "SignalLoggingName", "logsout", ...
    "SaveOutput", "off");

add_block("simulink/Sources/In1", modelName + "/pit_stop", ...
    "Position", [35 160 65 180]);

addConstant(modelName, "BaseLapTime", "base_lap_time_seconds", [35 25 115 55]);
addConstant(modelName, "PaceOffset", "pace_offset_seconds", [35 70 115 100]);
addConstant(modelName, "TyreDeg", "tyre_degradation_seconds_per_lap", [35 245 115 275]);
addConstant(modelName, "InitialFuelPenalty", "initial_fuel_penalty_seconds", [35 340 115 370]);
addConstant(modelName, "FuelGainPerLap", "fuel_gain_per_lap_seconds", [35 390 115 420]);
addConstant(modelName, "PitLoss", "pit_loss_seconds", [35 205 115 235]);
addConstant(modelName, "One", "1", [35 455 75 485]);
addConstant(modelName, "Zero", "0", [185 105 225 135]);

add_block("simulink/Discrete/Unit Delay", modelName + "/LapIndex", ...
    "InitialCondition", "0", "SampleTime", "1", ...
    "Position", [185 445 235 485]);
add_block("simulink/Math Operations/Add", modelName + "/NextLapIndex", ...
    "Inputs", "++", "Position", [285 445 315 485]);

add_block("simulink/Math Operations/Product", modelName + "/FuelBurn", ...
    "Position", [300 365 345 405]);
add_block("simulink/Math Operations/Add", modelName + "/FuelPenaltyRaw", ...
    "Inputs", "+-", "Position", [390 340 425 385]);
add_block("simulink/Discontinuities/Saturation", modelName + "/FuelPenalty", ...
    "LowerLimit", "0", "UpperLimit", "inf", ...
    "Position", [465 340 515 385]);

add_block("simulink/Discrete/Unit Delay", modelName + "/TyreAge", ...
    "InitialCondition", "initial_tyre_age_laps", "SampleTime", "1", ...
    "Position", [260 260 315 300]);
add_block("simulink/Math Operations/Add", modelName + "/NextTyreAge", ...
    "Inputs", "++", "Position", [365 260 395 300]);
add_block("simulink/Signal Routing/Switch", modelName + "/ResetTyreAfterPit", ...
    "Criteria", "u2 >= Threshold", "Threshold", "0.5", ...
    "Position", [445 235 495 315]);
add_block("simulink/Math Operations/Product", modelName + "/TyrePenalty", ...
    "Position", [365 205 410 240]);
add_block("simulink/Math Operations/Product", modelName + "/PitPenalty", ...
    "Position", [185 180 230 215]);

add_block("simulink/Math Operations/Add", modelName + "/LapTime", ...
    "Inputs", "+++++", "Position", [580 120 620 250]);
add_block("simulink/Discrete/Unit Delay", modelName + "/CumulativeState", ...
    "InitialCondition", "0", "SampleTime", "1", ...
    "Position", [680 285 735 325]);
add_block("simulink/Math Operations/Add", modelName + "/CumulativeTime", ...
    "Inputs", "++", "Position", [680 180 720 240]);

addOutport(modelName, "lap_time", 1, [810 125 840 145]);
addOutport(modelName, "cumulative_time", 2, [810 190 840 210]);
addOutport(modelName, "tyre_age", 3, [810 255 840 275]);
addOutport(modelName, "fuel_penalty", 4, [810 320 840 340]);
addOutport(modelName, "pit_penalty", 5, [810 385 840 405]);

add_line(modelName, "One/1", "NextLapIndex/1", "autorouting", "on");
add_line(modelName, "LapIndex/1", "NextLapIndex/2", "autorouting", "on");
add_line(modelName, "NextLapIndex/1", "LapIndex/1", "autorouting", "on");
add_line(modelName, "LapIndex/1", "FuelBurn/1", "autorouting", "on");
add_line(modelName, "FuelGainPerLap/1", "FuelBurn/2", "autorouting", "on");
add_line(modelName, "InitialFuelPenalty/1", "FuelPenaltyRaw/1", "autorouting", "on");
add_line(modelName, "FuelBurn/1", "FuelPenaltyRaw/2", "autorouting", "on");
add_line(modelName, "FuelPenaltyRaw/1", "FuelPenalty/1", "autorouting", "on");

add_line(modelName, "TyreAge/1", "NextTyreAge/1", "autorouting", "on");
add_line(modelName, "One/1", "NextTyreAge/2", "autorouting", "on");
add_line(modelName, "Zero/1", "ResetTyreAfterPit/1", "autorouting", "on");
add_line(modelName, "pit_stop/1", "ResetTyreAfterPit/2", "autorouting", "on");
add_line(modelName, "NextTyreAge/1", "ResetTyreAfterPit/3", "autorouting", "on");
add_line(modelName, "ResetTyreAfterPit/1", "TyreAge/1", "autorouting", "on");
add_line(modelName, "TyreAge/1", "TyrePenalty/1", "autorouting", "on");
add_line(modelName, "TyreDeg/1", "TyrePenalty/2", "autorouting", "on");
add_line(modelName, "pit_stop/1", "PitPenalty/1", "autorouting", "on");
add_line(modelName, "PitLoss/1", "PitPenalty/2", "autorouting", "on");

add_line(modelName, "BaseLapTime/1", "LapTime/1", "autorouting", "on");
add_line(modelName, "PaceOffset/1", "LapTime/2", "autorouting", "on");
add_line(modelName, "TyrePenalty/1", "LapTime/3", "autorouting", "on");
add_line(modelName, "FuelPenalty/1", "LapTime/4", "autorouting", "on");
add_line(modelName, "PitPenalty/1", "LapTime/5", "autorouting", "on");
add_line(modelName, "LapTime/1", "CumulativeTime/1", "autorouting", "on");
add_line(modelName, "CumulativeState/1", "CumulativeTime/2", "autorouting", "on");
add_line(modelName, "CumulativeTime/1", "CumulativeState/1", "autorouting", "on");

add_line(modelName, "LapTime/1", "lap_time/1", "autorouting", "on");
add_line(modelName, "CumulativeTime/1", "cumulative_time/1", "autorouting", "on");
add_line(modelName, "TyreAge/1", "tyre_age/1", "autorouting", "on");
add_line(modelName, "FuelPenalty/1", "fuel_penalty/1", "autorouting", "on");
add_line(modelName, "PitPenalty/1", "pit_penalty/1", "autorouting", "on");

logSignal(modelName + "/LapTime", "lap_time");
logSignal(modelName + "/CumulativeTime", "cumulative_time");
logSignal(modelName + "/TyreAge", "tyre_age");
logSignal(modelName + "/FuelPenalty", "fuel_penalty");
logSignal(modelName + "/PitPenalty", "pit_penalty");

Simulink.BlockDiagram.arrangeSystem(modelName);
save_system(modelName, modelPath);
close_system(modelName, 0);
clear cleanup;

fprintf("Built Simulink model: %s\n", modelPath);
end


function addConstant(modelName, blockName, value, position)
add_block("simulink/Sources/Constant", modelName + "/" + blockName, ...
    "Value", value, "SampleTime", "1", "Position", position);
end


function addOutport(modelName, blockName, port, position)
add_block("simulink/Sinks/Out1", modelName + "/" + blockName, ...
    "Port", string(port), "Position", position);
end


function logSignal(blockPath, signalName)
ports = get_param(blockPath, "PortHandles");
set_param(ports.Outport(1), "DataLogging", "on", "Name", signalName);
end


function closeIfLoaded(modelName)
if bdIsLoaded(modelName)
    close_system(modelName, 0);
end
end
