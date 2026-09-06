[CmdletBinding()]
param(
    [string]$Features = "outputs/driver_model_features.csv",
    [string]$Strategies = "outputs/strategy/predicted_tyre_strategy.csv",
    [string]$OutputDir = "outputs/matlab"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $pythonExecutable = $venvPython
}
else {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        $python = Get-Command py -ErrorAction SilentlyContinue
    }
    if ($python) {
        $pythonExecutable = $python.Source
    }
}
if (-not $pythonExecutable) {
    throw "Python was not found on PATH. Activate the project virtual environment first."
}

$matlab = Get-Command matlab -ErrorAction SilentlyContinue
if (-not $matlab) {
    throw "MATLAB was not found on PATH. MATLAB and Simulink are required."
}

Push-Location $repositoryRoot
try {
    & $pythonExecutable scripts/export_simulink_inputs.py `
        --features $Features `
        --strategies $Strategies `
        --output (Join-Path $OutputDir "lap_dynamics_inputs.csv")
    if ($LASTEXITCODE -ne 0) {
        throw "The Simulink input export failed with exit code $LASTEXITCODE."
    }

    $inputPath = (Resolve-Path (Join-Path $OutputDir "lap_dynamics_inputs.csv")).Path.Replace("'", "''")
    $resolvedOutputDir = (Resolve-Path $OutputDir).Path.Replace("'", "''")
    $matlabDir = (Resolve-Path "matlab").Path.Replace("'", "''")
    $batchCommand = "addpath('$matlabDir'); run_lap_dynamics('$inputPath','$resolvedOutputDir');"
    & $matlab.Source -batch $batchCommand
    if ($LASTEXITCODE -ne 0) {
        throw "The Simulink run failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
