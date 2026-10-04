param([ValidateSet('install','restore')][string]$Mode = 'install')
$ErrorActionPreference = 'Stop'
$panelRoot = Split-Path $PSScriptRoot -Parent
Push-Location $panelRoot
try {
    Write-Host "Persistent native counter: $Mode. NOR sectors 92b000 and ccd000 only." -ForegroundColor Cyan
    Write-Host 'Install replaces the original UI on boot. Restore writes both exact original sectors.'
    Read-Host 'Keep panel and nanoDAP powered and connected, then press Enter' | Out-Null
    & python -X utf8 analysis/persistence/run_native_counter_firmware.py $Mode --execute
    if ($LASTEXITCODE -ne 0) { throw 'Operation failed. Keep evidence and power state; do not blindly retry or reset.' }
}
finally { Pop-Location }
