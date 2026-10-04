$ErrorActionPreference = 'Stop'
$panelRoot = Split-Path $PSScriptRoot -Parent
$panelOpenOcd = Join-Path $panelRoot 'tools\xpack-openocd-0.12.0-7\bin\openocd.exe'
$panelStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$panelArchive = Join-Path $panelRoot "analysis\display-takeover\manual-pixels-$panelStamp"
New-Item -ItemType Directory -Path $panelArchive | Out-Null
Push-Location $panelRoot
try {
    Read-Host 'Wake the screen, then press Enter. A magenta strip will appear near one edge for 3 seconds' | Out-Null
    foreach ($panelCount in 3, 2, 1) {
        Write-Host "Pixel test starts in $panelCount..." -ForegroundColor Cyan
        Start-Sleep -Seconds 1
    }
    Write-Host 'Watch the panel. Backing up the strip takes several seconds, then the color appears.' -ForegroundColor Green
    $panelAttemptStart = Get-Date
    & $panelOpenOcd -s diagnostics -f diagnostics/display-pixels-session.cfg -l diagnostics/display-pixels-session.txt
    $panelReturnCode = $LASTEXITCODE
    foreach ($panelName in 'display-pixels-session.txt', 'display-pixels-session-result.txt', 'display-pixels-mcu-result.txt') {
        if ((Test-Path "diagnostics/$panelName") -and
            (Get-Item "diagnostics/$panelName").LastWriteTime -ge $panelAttemptStart) {
            Copy-Item -LiteralPath "diagnostics/$panelName" -Destination $panelArchive
        }
    }
    foreach ($panelPattern in 'pixel-strip-*.bin', 'pixels-scratch-*.bin') {
        Get-ChildItem backups/display-takeover -Filter $panelPattern |
            Where-Object { $_.LastWriteTime -ge $panelAttemptStart } | Copy-Item -Destination $panelArchive
    }
    if ($panelReturnCode -ne 0) { throw 'Pixel test did not complete; report the output before running another device command.' }
    Write-Host 'Pixels, MCU context, MPU settings, A7 execution and debug locks restored.' -ForegroundColor Green
    Write-Host "Evidence saved: $panelArchive"
}
finally { Pop-Location }
