# Restore data\me.db from a backup file.
# All console text is ASCII on purpose: PS 5.1 reads BOM-less files as ANSI.
#
#   powershell -ExecutionPolicy Bypass -File scripts\restore.ps1 -List
#   powershell -ExecutionPolicy Bypass -File scripts\restore.ps1 -File backups\me-20261111-210105.db -Yes
#
# The current db is kept as data\me.db.before-restore (one slot, overwritten each
# time). The server is stopped before the swap and started again afterwards.

param(
    [string]$File,
    [switch]$List,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Db = Join-Path $Root "data\me.db"
$Backups = Join-Path $Root "backups"
$RunPs1 = Join-Path $Root "run.ps1"

if ($List) {
    if (-not (Test-Path $Backups)) { Write-Host "[ .. ] no backups dir yet"; exit 0 }
    Get-ChildItem $Backups -Filter "me-*.db" | Sort-Object Name -Descending | ForEach-Object {
        $kb = [math]::Round($_.Length / 1KB)
        Write-Host ("{0}  {1} KB" -f $_.Name, $kb)
    }
    exit 0
}

if (-not $File) { Write-Host "[FAIL] pass -File <path> (see -List)"; exit 1 }
$Src = (Resolve-Path $File).Path
if (-not (Test-Path $Src)) { Write-Host "[FAIL] no such file: $Src"; exit 1 }
if (-not $Yes) {
    Write-Host "about to replace : $Db"
    Write-Host "with             : $Src"
    Write-Host "current db will be kept as data\me.db.before-restore"
    Write-Host "re-run with -Yes to do it"
    exit 2
}

if (Test-Path $RunPs1) {
    & powershell -ExecutionPolicy Bypass -File $RunPs1 -Stop | Out-Null
}
if (Test-Path $Db) { Copy-Item $Db (Join-Path $Root "data\me.db.before-restore") -Force }
Get-ChildItem (Join-Path $Root "data") -Filter "me.db-*" -ErrorAction SilentlyContinue | Remove-Item -Force
Copy-Item $Src $Db -Force
Write-Host "[ OK ] restored $Db from $Src"

if (Test-Path $RunPs1) {
    & powershell -ExecutionPolicy Bypass -File $RunPs1 -Background | Out-Null
    Start-Sleep -Seconds 2
    try {
        $h = Invoke-RestMethod "http://127.0.0.1:8000/api/health" -TimeoutSec 5
        Write-Host ("[ OK ] server up, messages = " + $h.messages)
    } catch {
        Write-Host "[ .. ] server not reachable yet, run: .\run.ps1 -Background"
    }
}
exit 0
