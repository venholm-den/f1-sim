param(
    [ValidateRange(15, 360)]
    [int]$IntervalMinutes = 60,
    [ValidateRange(100, 100000)]
    [int]$SimulationCount = 10000,
    [switch]$EnableDiscord,
    [switch]$EnablePostRace,
    [switch]$EnableWeekendBriefing,
    [string]$TaskName = "F1 Sim - Session Forecast"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Project Python environment not found at $Python. Complete docs\setup.md first."
}

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    throw "Scheduled task '$TaskName' already exists. It was not changed."
}

$Arguments = "-m scripts.auto_forecast --n-sims $SimulationCount"
if ($EnableDiscord) {
    $Arguments += " --discord"
}
if ($EnablePostRace) {
    $Arguments += " --post-race"
}
if ($EnableWeekendBriefing) {
    $Arguments += " --weekend-briefing"
}
$Action = New-ScheduledTaskAction -Execute $Python -Argument $Arguments -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Principal $Principal `
    -Description "Checks for newly eligible F1 sessions and creates one local frozen forecast per session."

Write-Host "Installed '$TaskName'. First check is in about five minutes, then every $IntervalMinutes minutes."
Write-Host "The task only runs while this Windows user is logged on."
