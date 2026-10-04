param([ValidateRange(2,180)][int]$Seconds = 60, [switch]$ReadOnly)
$ErrorActionPreference = 'Stop'
$panelRoot = Split-Path $PSScriptRoot -Parent
Push-Location $panelRoot
try {
    Write-Host 'Temporary RAM pixel test. A7 and the original GUI keep running; Flash is unchanged.' -ForegroundColor Cyan
    Write-Host 'Touches also reach the original GUI. Open a screen with a blank area and tap there.' -ForegroundColor Yellow
    Read-Host 'Wake the screen, lift your finger, then press Enter to start' | Out-Null
    foreach ($panelCount in 3, 2, 1) {
        Write-Host "Touch counter starts in $panelCount..." -ForegroundColor Cyan
        Start-Sleep -Seconds 1
    }
    $panelArguments = @('-X', 'utf8', 'analysis/display-takeover/run_touch_counter.py', '--seconds', "$Seconds")
    if ($ReadOnly) { $panelArguments += '--read-only' }
    & python @panelArguments
    if ($LASTEXITCODE -ne 0) { throw 'Touch counter stopped; see its saved result before retrying.' }
    Write-Host 'Counter finished; temporary pixel overlay removed. Original firmware continues running.' -ForegroundColor Green
}
finally { Pop-Location }
