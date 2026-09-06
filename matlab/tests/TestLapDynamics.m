classdef TestLapDynamics < matlab.unittest.TestCase
    methods (TestClassSetup)
        function addProjectPaths(~)
            matlabDir = fileparts(fileparts(mfilename("fullpath")));
            addpath(matlabDir);
            build_lap_dynamics_model(fullfile(matlabDir, "models"));
            addpath(fullfile(matlabDir, "models"));
        end
    end

    methods (Test)
        function pitStopAddsLossAndResetsTyreAge(testCase)
            tempDir = string(tempname);
            mkdir(tempDir);
            testCase.addTeardown(@()rmdir(tempDir, "s"));

            input = table( ...
                "TST", "Test Team", 5, 80.0, 0.2, 0.1, 0, 1.0, 0.2, ...
                1, "3", 20.0, ...
                'VariableNames', {'Driver', 'Team', 'race_laps', ...
                'base_lap_time_seconds', 'pace_offset_seconds', ...
                'tyre_degradation_seconds_per_lap', 'initial_tyre_age_laps', ...
                'initial_fuel_penalty_seconds', 'fuel_gain_per_lap_seconds', ...
                'expected_stops', 'pit_laps', 'pit_loss_seconds'});
            inputPath = fullfile(tempDir, "inputs.csv");
            writetable(input, inputPath);

            [detailPath, summaryPath] = run_lap_dynamics(inputPath, tempDir);
            detail = readtable(detailPath, "TextType", "string");
            summary = readtable(summaryPath, "TextType", "string");

            testCase.verifyEqual(height(detail), 5);
            testCase.verifyEqual(detail.pit_penalty_seconds', [0 0 20 0 0], "AbsTol", 1e-12);
            testCase.verifyEqual(detail.tyre_age_laps', [0 1 2 0 1], "AbsTol", 1e-12);
            testCase.verifyEqual(summary.simulated_race_time_seconds, ...
                sum(detail.lap_time_seconds), "AbsTol", 1e-9);
            testCase.verifyEqual(summary.pit_stops, 1);
        end
    end
end
