param([ValidateSet('install','restore')][string]$Mode = 'install')
$ErrorActionPreference = 'Stop'
$panelRoot = Split-Path $PSScriptRoot -Parent
Push-Location $panelRoot
try {
    Write-Host "Persistent native GitHub tap fast: $Mode. Only NOR sectors 92b000, 95a000 and ccd000." -ForegroundColor Cyan
    Write-Host 'Install requires the exact current tap v1 triple. Restore returns tap v1 and its exact auxiliary page.'
    Write-Host 'This improves tap responsiveness; the service interruption and bounded three-page scope remain unchanged.'
    Write-Host 'Both operations interrupt panel service and reboot once. Frozen inputs are checked before device access.'
    Read-Host 'Keep panel and nanoDAP powered and connected, then press Enter' | Out-Null
    & python -X utf8 analysis/persistence/run_native_github_tap_fast_firmware.py $Mode --execute
    if ($LASTEXITCODE -ne 0) { throw 'Operation failed. Preserve evidence and power state; do not blindly retry or reset.' }
}
finally { Pop-Location }
