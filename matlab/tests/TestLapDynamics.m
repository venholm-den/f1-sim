classdef TestLapDynamics < matlab.unittest.TestCase
    methods (TestClassSetup)
        function addProjectPaths(~)
            matlabDir = fileparts(fileparts(mfilename("fullpath")));
            addpath(matlabDir);
            if ~isfile(fullfile(matlabDir, "models", "f1_lap_dynamics_model.slx"))
                build_lap_dynamics_model(fullfile(matlabDir, "models"));
            end
            addpath(fullfile(matlabDir, "models"));
        end
    end

    methods (Test)
        function multiStopFuelFloorAndZeroCostPit(testCase)
            tempDir = string(tempname);
            mkdir(tempDir);
            testCase.addTeardown(@()rmdir(tempDir, 's'));
            cases = table(["ZERO"; "ONE"; "TWO"; "THREE"; "FREE"], ...
                repmat("Test",5,1), repmat(8,5,1), repmat(80,5,1), zeros(5,1), ...
                repmat(0.1,5,1), repmat(2,5,1), ones(5,1), repmat(0.5,5,1), ...
                [0;1;2;3;1], ["";"4";"2;5";"2;4;6";"4"], [20;20;20;20;0], ...
                'VariableNames', {'Driver','Team','race_laps','base_lap_time_seconds', ...
                'pace_offset_seconds','tyre_degradation_seconds_per_lap','initial_tyre_age_laps', ...
                'initial_fuel_penalty_seconds','fuel_gain_per_lap_seconds', ...
                'expected_stops','pit_laps','pit_loss_seconds'});
            inputPath = fullfile(tempDir, 'inputs.csv');
            writetable(cases,inputPath);
            [detailPath,summaryPath] = run_lap_dynamics(inputPath,tempDir,false);
            detail = readtable(detailPath,'TextType','string');
            summary = readtable(summaryPath,'TextType','string');
            expectedAge = [2 3 4 5 6 7 8 9; 2 3 4 5 0 1 2 3; ...
                2 3 0 1 2 0 1 2; 2 3 0 1 0 1 0 1; 2 3 4 5 0 1 2 3];
            for k = 1:height(cases)
                rows = detail.Driver == cases.Driver(k);
                testCase.verifyEqual(detail.tyre_age_laps(rows)',expectedAge(k,:),'AbsTol',1e-12);
                testCase.verifyEqual(detail.fuel_penalty_seconds(rows)',[1 .5 0 0 0 0 0 0],'AbsTol',1e-12);
                expectedTotal = 640 + 1.5 + sum(expectedAge(k,:))*.1 + cases.expected_stops(k)*cases.pit_loss_seconds(k);
                result = summary(summary.Driver == cases.Driver(k),:);
                testCase.verifyEqual(result.simulated_race_time_seconds,expectedTotal,'AbsTol',1e-9);
                testCase.verifyEqual(result.pit_stops,cases.expected_stops(k));
            end
            % Rejected before sim(): malformed, duplicate, fractional, final-lap and mismatched schedules.
            invalid = ["2;x"; "2;2"; "2.5"; "8"; "2;5"];
            for schedule = invalid'
                row = cases(2,:);
                row.pit_laps = schedule;
                writetable(row,inputPath);
                testCase.verifyError(@()read_lap_cases(inputPath),'f1sim:InvalidInputContract');
            end
            row = cases(1,:);
            row.fuel_gain_per_lap_seconds = NaN;
            writetable(row,inputPath);
            testCase.verifyError(@()read_lap_cases(inputPath),'f1sim:InvalidInputContract');
        end

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
