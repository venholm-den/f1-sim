param(
    [string]$Name = "F1RaceSimulatorPortable"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$WorkPath = Join-Path ([System.IO.Path]::GetTempPath()) "f1-sim-pyinstaller-$Name"

if (-not (Test-Path $Python)) {
    $Python = "python"
}

if (Test-Path $WorkPath) {
    Remove-Item -LiteralPath $WorkPath -Recurse -Force
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name $Name `
    --workpath $WorkPath `
    --add-data "config;config" `
    --add-data "data\fantasy_prices.csv;data" `
    --add-data "data\team_power_units.csv;data" `
    --add-data "data\track_profiles.csv;data" `
    --add-data "data\fia_documents;data\fia_documents" `
    --add-data "assets;assets" `
    --add-data "portable_app\web;portable_app\web" `
    --collect-data fastf1 `
    --collect-all webview `
    --collect-all pythonnet `
    --collect-all clr_loader `
    portable_app\web_main.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Build complete: dist\$Name\$Name.exe"
