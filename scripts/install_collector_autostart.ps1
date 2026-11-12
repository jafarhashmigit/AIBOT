# AIBOT Phase67 read-only collector — Windows Task Scheduler helper
# NO credentials. NO broker writes. NO order_send.
# Reboot recovery is NOT claimed until you reboot and verify.
param(
  [ValidateSet("install","uninstall","verify","help")]
  [string]$Action = "help"
)

$ErrorActionPreference = "Stop"
$TaskName = "AIBOT_Phase67_Exness_RO_Collector"
$ProjectRoot = "C:\Users\Dell\Documents\1\AIBOT"
$Python = "C:\Users\Dell\Documents\1\AIBOT\.venv\Scripts\python.exe"
$WorkDir = $ProjectRoot

function Install-AibotCollectorTask {
    if (-not (Test-Path $Python)) { throw "Python not found: $Python" }
    schtasks /Query /TN $TaskName 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        schtasks /Delete /TN $TaskName /F | Out-Null
    }
    $tr = "`"$Python`" -m phase67.cli start --interval 30 --m5-lookback 50"
    # ONSTART with delay; current user interactive. Credentials are not embedded in this file.
    schtasks /Create /TN $TaskName /SC ONSTART /DELAY 0002:00 /RL LIMITED /RU "$env:USERNAME" /IT /TR $tr /F
    if ($LASTEXITCODE -ne 0) { throw "schtasks create failed: $LASTEXITCODE" }
    Write-Host "Installed $TaskName. Verify with: schtasks /Query /TN $TaskName /V /FO LIST"
    Write-Host "IMPORTANT: Reboot recovery is UNTESTED until you reboot and confirm collector health."
}

function Uninstall-AibotCollectorTask {
    schtasks /Delete /TN $TaskName /F
}

function Verify-AibotCollectorTask {
    schtasks /Query /TN $TaskName /V /FO LIST
    Set-Location $WorkDir
    $env:PYTHONPATH = Join-Path $WorkDir "src"
    & $Python -m phase67.cli health
}

switch ($Action) {
  "install"   { Install-AibotCollectorTask }
  "uninstall" { Uninstall-AibotCollectorTask }
  "verify"    { Verify-AibotCollectorTask }
  default {
    Write-Host "Actions: install | uninstall | verify"
    Write-Host "Example: powershell -ExecutionPolicy Bypass -File .\scripts\install_collector_autostart.ps1 -Action install"
  }
}
