# 启动 / 停止 分身志
#
#   .\run.ps1              前台启动（Ctrl + C 停止）
#   .\run.ps1 -Background  后台启动，关掉这个窗口也不停
#   .\run.ps1 -Stop        停止后台进程
#
# 首次使用前先执行：
#   D:\python\python3.12.2\python.exe -m venv .venv
#   .\.venv\Scripts\python.exe -m pip install -r requirements.txt

param(
    [switch]$Background,
    [switch]$Stop,
    [switch]$Restart
)

$root = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$pidFile = Join-Path $root ".run.pid"
$port = 8000
$localUrl = "http://127.0.0.1:$port"

function Get-LanUrl {
    $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notlike "127.*" -and
            $_.IPAddress -notlike "169.254.*" -and
            $_.PrefixOrigin -ne "WellKnown"
        } |
        Sort-Object -Property @{ Expression = { $_.InterfaceAlias -match "WLAN|Wi-Fi|以太网|Ethernet" } } -Descending |
        Select-Object -First 1
    if ($ip) { return "http://$($ip.IPAddress):$port" }
    return ""
}

function Stop-Server {
    $stopped = $false
    if (Test-Path $pidFile) {
        $oldPid = (Get-Content $pidFile -Raw).Trim()
        if ($oldPid) {
            Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
            $stopped = $true
        }
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    }
    # 兜底：不管 pid 文件，把占着端口的进程也停掉
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object {
            Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
            $stopped = $true
        }
    if ($stopped) { Write-Host "已停止" -ForegroundColor Yellow }
    else { Write-Host "没有在跑" -ForegroundColor DarkGray }
}

if ($Restart) {
    Stop-Server
    Start-Sleep -Seconds 1
    $Background = $true
}

if ($Stop) {
    Stop-Server
    exit 0
}

if (-not (Test-Path $python)) {
    Write-Host "找不到虚拟环境：$python" -ForegroundColor Red
    Write-Host "先执行：D:\python\python3.12.2\python.exe -m venv .venv"
    exit 1
}

if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    $alive = $false
    try { $null = Invoke-RestMethod "$localUrl/api/health" -TimeoutSec 3; $alive = $true } catch { }
    if ($alive) {
        Write-Host "已经在跑了（$localUrl 有响应），不用再启动" -ForegroundColor Yellow
        Write-Host "  本机：$localUrl"
        $lanNow = Get-LanUrl
        if ($lanNow) { Write-Host "  手机：$lanNow" }
        Write-Host "  要重启执行 .\run.ps1 -Restart"
        exit 0
    }
    Write-Host "端口 $port 被别的程序占用了，先执行 .\run.ps1 -Stop 再启动" -ForegroundColor Red
    exit 1
}

Set-Location $root
$lanUrl = Get-LanUrl

if ($Background) {
    $proc = Start-Process -FilePath $python `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$port" `
        -WorkingDirectory $root -WindowStyle Hidden -PassThru
    $proc.Id | Set-Content -Path $pidFile -Encoding ascii
    Start-Sleep -Seconds 3
    try {
        $null = Invoke-RestMethod "$localUrl/api/health" -TimeoutSec 5
        Write-Host "已后台启动（PID $($proc.Id)）" -ForegroundColor Green
    } catch {
        Write-Host "启动失败：先用前台模式 .\run.ps1 看报错" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "分身志 启动中（Ctrl + C 停止）" -ForegroundColor Green
}

Write-Host "  本机：$localUrl"
if ($lanUrl) {
    Write-Host "  手机：$lanUrl  （同一个 WiFi）"
    Write-Host "  手机连不上就跑这条（管理员 PowerShell，只需一次）：" -ForegroundColor DarkGray
    Write-Host '  New-NetFirewallRule -DisplayName "分身志 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow -Profile Private,Public' -ForegroundColor DarkGray
}

if (-not $Background) {
    & $python -m uvicorn app.main:app --host 0.0.0.0 --port $port
}

