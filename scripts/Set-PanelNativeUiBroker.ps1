param([ValidateSet('install','restore')][string]$Mode = 'install')
$ErrorActionPreference = 'Stop'
$panelRoot = Split-Path $PSScriptRoot -Parent
Push-Location $panelRoot
try {
    Write-Host "Persistent native UI broker: $Mode. Only NOR sectors 92b000 and ccd000." -ForegroundColor Cyan
    Write-Host 'Install starts stock UI once and adds physical-key switching. It replaces factory/diagnostic demos.'
    Write-Host 'Restore writes the two exact original sectors. Both operations interrupt service and reboot once.'
    Read-Host 'Keep panel and nanoDAP powered and connected, then press Enter' | Out-Null
    & python -X utf8 analysis/persistence/run_native_ui_broker_firmware.py $Mode --execute
    if ($LASTEXITCODE -ne 0) { throw 'Operation failed. Preserve evidence and power state; do not blindly retry or reset.' }
}
finally { Pop-Location }
