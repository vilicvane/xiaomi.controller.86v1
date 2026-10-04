param([ValidateSet('install','restore')][string]$Mode = 'install')
$ErrorActionPreference = 'Stop'
$panelRoot = Split-Path $PSScriptRoot -Parent
Push-Location $panelRoot
try {
    Write-Host "Persistent native drawer: $Mode. Only NOR sectors 92b000 and ccd000." -ForegroundColor Cyan
    Write-Host 'Install requires the exact verified UI broker v1. Restore returns that broker and its third-key switching.'
    Write-Host 'Drawer borrows the audited unused wifi_recorder worker and disables its diagnostic command.'
    Write-Host 'Both operations interrupt panel service and reboot once. Frozen inputs are checked before device access.'
    Read-Host 'Keep panel and nanoDAP powered and connected, then press Enter' | Out-Null
    & python -X utf8 analysis/persistence/run_native_drawer_firmware.py $Mode --execute
    if ($LASTEXITCODE -ne 0) { throw 'Operation failed. Preserve evidence and power state; do not blindly retry or reset.' }
}
finally { Pop-Location }
