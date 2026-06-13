$changedFiles = git diff --cached --name-only

# Gate commits when source/config files changed, since those changes often impact
# setup, outputs, or behavior that should be reflected in README.md.
$codeChanged = $changedFiles | Where-Object {
    $_ -match '\.(ts|tsx|js|jsx|py|json|css|html)$' -or
    $_ -match 'capabilities\.json' -or
    $_ -match 'pbiviz\.json' -or
    $_ -match 'package\.json'
}

$readmeChanged = $changedFiles | Where-Object {
    $_ -match '(^|/)README\.md$'
}

if ($codeChanged -and -not $readmeChanged) {
    Write-Host ""
    Write-Host "Code/config files changed, but README.md was not updated." -ForegroundColor Yellow
    Write-Host "Run this in VS Code Copilot Chat before committing:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  /update-readme" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Changed files:"
    $codeChanged | ForEach-Object { Write-Host "  - $_" }

    Write-Host ""
    # Allow an explicit override so urgent commits are not blocked, while keeping
    # a conservative default that prevents accidental doc drift.
    $answer = Read-Host "Continue commit anyway? y/N"

    if ($answer -ne "y" -and $answer -ne "Y") {
        exit 1
    }
}

exit 0