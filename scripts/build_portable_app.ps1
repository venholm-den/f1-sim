param(
    [string]$Name = "F1RaceSimulatorPortable"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    $Python = "python"
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name $Name `
    --add-data "config;config" `
    --add-data "data;data" `
    --add-data "assets;assets" `
    --add-data "portable_app\web;portable_app\web" `
    --collect-data fastf1 `
    --collect-all webview `
    --collect-all pythonnet `
    --collect-all clr_loader `
    portable_app\web_main.py

Write-Host ""
Write-Host "Build complete: dist\$Name\$Name.exe"
