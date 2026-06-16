param(
    [string]$Name = "F1SimGUI"
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
    app_gui.py

Write-Host ""
Write-Host "Build complete: dist\$Name\$Name.exe"
