param(
    [Parameter(Mandatory = $true)]
    [string]$RuntimePath,
    [Parameter(Mandatory = $true)]
    [string]$InspectionReport
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$RuntimeRoot = [System.IO.Path]::GetFullPath($RuntimePath)
$ProjectPrefix = $ProjectRoot.TrimEnd('\') + '\'
if ($RuntimeRoot -eq $ProjectRoot -or $RuntimeRoot.StartsWith($ProjectPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Choose a new runtime folder outside the development checkout.'
}
if (Test-Path -LiteralPath $RuntimeRoot) {
    throw 'The runtime folder already exists. Choose a new version; never overwrite a sealed runtime.'
}
if (-not (Test-Path -LiteralPath $Python) -or -not (Test-Path -LiteralPath $InspectionReport)) {
    throw 'The existing project Python and a consolidated inspection report are required.'
}

New-Item -ItemType Directory -Path $RuntimeRoot | Out-Null
# Tracked source/resources only. Credentials, caches and user archives are not copied.
$TrackedFiles = & git -C $ProjectRoot ls-files
if ($LASTEXITCODE -ne 0) { throw 'Cannot enumerate tracked source files.' }
foreach ($Relative in $TrackedFiles) {
    if ($Relative -notmatch '^(src/|scripts/|portable_app/|config/|assets/|matlab/|main\.py$|requirements(-dev)?\.txt$|LICENSE$)') { continue }
    $Source = Join-Path $ProjectRoot $Relative
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { continue }
    $Destination = Join-Path $RuntimeRoot $Relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination
}
foreach ($Name in @('prediction_trials.json', 'stage_ensemble_shadow.json', 'classification_checks.json', 'fia_sync.json', 'form_shadow.json')) {
    $Source = Join-Path $ProjectRoot "config\$Name"
    if (Test-Path -LiteralPath $Source) {
        Copy-Item -LiteralPath $Source -Destination (Join-Path $RuntimeRoot "config\$Name")
    }
}
foreach ($Name in @('data', 'outputs')) {
    New-Item -ItemType Junction -Path (Join-Path $RuntimeRoot $Name) -Target (Join-Path $ProjectRoot $Name) | Out-Null
}

Push-Location $RuntimeRoot
try {
    & $Python -m scripts.prediction_trials --renew-existing --inspected-reports $InspectionReport
    if ($LASTEXITCODE -ne 0) { throw 'Suite renewal failed; the scheduled task was not changed.' }
    & $Python -m scripts.forecast_runtime seal --workspace $ProjectRoot
    if ($LASTEXITCODE -ne 0) { throw 'Runtime sealing failed; the scheduled task was not changed.' }
    & $Python -m scripts.forecast_runtime verify
    if ($LASTEXITCODE -ne 0) { throw 'Runtime verification failed; the scheduled task was not changed.' }
} finally {
    Pop-Location
}
Write-Output "Verified runtime: $RuntimeRoot"
Write-Output 'Task routing is a separate deployment step. Preserve its trigger, options and original XML.'
