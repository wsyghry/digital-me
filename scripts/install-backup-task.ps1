# Install / remove the daily backup task (Windows Task Scheduler).
# All console text is ASCII on purpose: PS 5.1 reads BOM-less files as ANSI.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install-backup-task.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install-backup-task.ps1 -Time 23:30 -Keep 30
#   powershell -ExecutionPolicy Bypass -File scripts\install-backup-task.ps1 -Remove

param(
    [string]$Time = "21:00",
    [int]$Keep = 14,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$TaskName = "digital-me-backup"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Backup = Join-Path $Root "scripts\backup.py"

if ($Remove) {
    schtasks /Delete /TN $TaskName /F 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Host "[ OK ] removed task $TaskName" }
    else { Write-Host "[ .. ] task $TaskName not found" }
    exit 0
}

if (-not (Test-Path $Python)) { Write-Host "[FAIL] missing $Python"; exit 1 }
if (-not (Test-Path $Backup)) { Write-Host "[FAIL] missing $Backup"; exit 1 }

$Command = "`"$Python`" `"$Backup`" --keep $Keep"
Write-Host "task   : $TaskName"
Write-Host "when   : daily $Time"
Write-Host "action : $Command"

schtasks /Create /TN $TaskName /TR $Command /SC DAILY /ST $Time /F | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] schtasks returned $LASTEXITCODE"; exit 1 }

Write-Host "[ OK ] daily backup registered. Run it once now to verify:"
Write-Host "       schtasks /Run /TN $TaskName"
Write-Host "       $Python scripts\backup.py --list"
exit 0
