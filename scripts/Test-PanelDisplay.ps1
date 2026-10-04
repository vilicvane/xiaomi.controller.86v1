param([ValidateRange(2, 30)][int]$DurationSeconds = 8)
$ErrorActionPreference = 'Stop'
$panelRoot = Split-Path $PSScriptRoot -Parent
$panelOpenOcd = Join-Path $panelRoot 'tools\xpack-openocd-0.12.0-7\bin\openocd.exe'
$panelStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$panelArchive = Join-Path $panelRoot "analysis\display-takeover\manual-bars-$panelStamp"
New-Item -ItemType Directory -Path $panelArchive | Out-Null
Push-Location $panelRoot
$panelAttempted = $false
try {
    Read-Host 'Wake the panel screen, then press Enter to start' | Out-Null
    foreach ($panelCount in 3, 2, 1) {
        Write-Host "Display test starts in $panelCount..." -ForegroundColor Cyan
        Start-Sleep -Seconds 1
    }
    $panelAttempted = $true
    & $panelOpenOcd -s diagnostics -f diagnostics/display-dsi-bars-probe.cfg -l diagnostics/display-dsi-bars-probe.txt
    if ($LASTEXITCODE -ne 0) { throw 'OpenOCD probe failed. See diagnostics/display-dsi-bars-probe.txt.' }
    $panelResult = Get-Content diagnostics/display-dsi-bars-probe-result.txt -Raw
    if ($panelResult -notmatch '(?m)^execution_verified 1\r?$' -or
        $panelResult -notmatch '(?m)^restore_complete 1\r?$') {
        throw 'RAM execution or CPU context restoration was not confirmed. See the result file.'
    }
    Write-Host "TEST ACTIVE: observe the screen for $DurationSeconds seconds." -ForegroundColor Green
    Start-Sleep -Seconds $DurationSeconds
}
finally {
    if ($panelAttempted -and (Test-Path diagnostics/display-dsi-bars-restore.cfg)) {
        Write-Host 'Restoring original display configuration...' -ForegroundColor Cyan
        & $panelOpenOcd -s diagnostics -f diagnostics/display-dsi-bars-restore.cfg -l diagnostics/display-dsi-bars-restore.txt
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Display restore failed; report the error before another test.' }
        foreach ($panelName in 'display-dsi-bars-probe.cfg', 'display-dsi-bars-probe.txt',
            'display-dsi-bars-probe-result.txt', 'display-dsi-bars-restore.cfg', 'display-dsi-bars-restore.txt') {
            if (Test-Path "diagnostics/$panelName") { Copy-Item -LiteralPath "diagnostics/$panelName" -Destination $panelArchive }
        }
        Get-ChildItem backups/display-takeover -Filter 'dsi-bars-scratch-*.bin' | Copy-Item -Destination $panelArchive
        Write-Host "Evidence saved: $panelArchive"
    }
    Pop-Location
}
