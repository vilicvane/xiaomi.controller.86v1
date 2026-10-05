param([ValidateSet('install','restore')][string]$Mode = 'install')
$ErrorActionPreference = 'Stop'
$panelRoot = Split-Path $PSScriptRoot -Parent
Push-Location $panelRoot
try {
    Write-Host "Persistent native GitHub tap: $Mode. Only NOR sectors 92b000, 95a000 and ccd000." -ForegroundColor Cyan
    Write-Host 'Install requires the exact verified GitHub card. Restore returns the original card without temporary tap feedback.'
    Write-Host 'This adds temporary cumulative tap feedback. Restore returns the original card and exact auxiliary page.'
    Write-Host 'Both operations interrupt panel service and reboot once. Frozen inputs are checked before device access.'
    Read-Host 'Keep panel and nanoDAP powered and connected, then press Enter' | Out-Null
    & python -X utf8 analysis/persistence/run_native_github_tap_firmware.py $Mode --execute
    if ($LASTEXITCODE -ne 0) { throw 'Operation failed. Preserve evidence and power state; do not blindly retry or reset.' }
}
finally { Pop-Location }
