param(
    [ValidatePattern('^[A-Za-z][A-Za-z0-9_.-]{0,70}$')]
    [string]$Name = "RaceWorkbenchBeta-0.2.0-beta.2"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$WorkPath = Join-Path ([System.IO.Path]::GetTempPath()) ("f1-sim-build-" + [guid]::NewGuid().ToString('N'))
$ReleasePath = Join-Path $ProjectRoot "dist\$Name"

if (-not (Test-Path $Python)) {
    $Python = "python"
}

if (Test-Path -LiteralPath $ReleasePath) {
    throw "Release already exists at $ReleasePath. Choose a new -Name; builds never overwrite a release."
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name $Name `
    --workpath $WorkPath `
    --add-data "config\default_run_config.json;config" `
    --add-data "data\fantasy_prices.csv;data" `
    --add-data "data\team_power_units.csv;data" `
    --add-data "data\track_profiles.csv;data" `
    --add-data "data\fia_documents\fia_document_index.csv;data\fia_documents" `
    --add-data "assets;assets" `
    --add-data "portable_app\web;portable_app\web" `
    --add-data "src;src" `
    --add-data "scripts;scripts" `
    --add-data "main.py;." `
    --add-data "requirements.txt;." `
    --add-data "matlab;matlab" `
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
Copy-Item -LiteralPath "$ProjectRoot\docs\windows-beta.md" -Destination "$ReleasePath\START-HERE.md"
Copy-Item -LiteralPath "$ProjectRoot\docs\portable-ui-functionality.md" -Destination "$ReleasePath\FUNCTIONALITY.md"
Copy-Item -LiteralPath "$ProjectRoot\docs\historical-data-library.md" -Destination "$ReleasePath\HISTORICAL-DATA.md"
Copy-Item -LiteralPath "$ProjectRoot\docs\model-training.md" -Destination "$ReleasePath\MODEL-TRAINING.md"
Copy-Item -LiteralPath "$ProjectRoot\docs\desktop-ui-and-pc-runs.md" -Destination "$ReleasePath\PC-RUNS.md"
Copy-Item -LiteralPath "$ProjectRoot\docs\fantasy-data-archive.md" -Destination "$ReleasePath\fantasy-data-archive.md"
Copy-Item -LiteralPath "$ProjectRoot\docs\reference-data.md" -Destination "$ReleasePath\REFERENCE-DATA.md"
Copy-Item -LiteralPath "$ProjectRoot\LICENSE" -Destination "$ReleasePath\LICENSE"
Compress-Archive -LiteralPath $ReleasePath -DestinationPath "$ReleasePath.zip"
Get-FileHash -LiteralPath "$ReleasePath.zip" -Algorithm SHA256 | Format-List
