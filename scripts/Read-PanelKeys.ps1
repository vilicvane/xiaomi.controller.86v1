param()
$ErrorActionPreference = 'Stop'
$panelRoot = Split-Path $PSScriptRoot -Parent
Push-Location $panelRoot
try {
    Write-Host 'Read-only key mapping: no halt, reset, RAM write or Flash write.' -ForegroundColor Cyan
    Write-Host 'During the 30-second capture, press ONLY your third key three times.'
    Write-Host 'Hold each press about 0.2 seconds; leave about 1 second between presses.'
    Read-Host 'Prepare your hand, then press Enter to start the countdown' | Out-Null
    foreach ($panelCount in 3,2,1) {
        Write-Host "Key capture starts in $panelCount..."
        Start-Sleep -Seconds 1
    }
    Write-Host 'CAPTURE STARTED: press key 3 now.' -ForegroundColor Green
    & .\tools\xpack-openocd-0.12.0-7\bin\openocd.exe -s diagnostics -f diagnostics/read-physical-keys.cfg -l diagnostics/physical-key3-manual.txt
    if ($LASTEXITCODE -ne 0) { throw 'Read-only capture failed. See diagnostics/physical-key3-manual.txt.' }
    Select-String -LiteralPath diagnostics/physical-key3-manual.txt -Pattern '^PHYSICAL_KEYS' | ForEach-Object { Write-Host $_.Line }
    Write-Host 'Capture complete. The saved log can be read directly from this workspace.'
}
finally { Pop-Location }
