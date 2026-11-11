<#
接话挂件：开一个 380x640 的独立小窗口，常驻屏幕上，显示「谁在等你回话」。

用法：
  .\scripts\widget.ps1              # 开小窗并置顶
  .\scripts\widget.ps1 -NoTop       # 不置顶
  .\scripts\widget.ps1 -Width 420 -Height 720

它只是打开 http://127.0.0.1:8000/widget.html，不做任何发消息的动作。
#>
param(
  [int]$Width = 380,
  [int]$Height = 640,
  [switch]$NoTop
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$base = "http://127.0.0.1:8000"

# 1. 服务没起就先起
$alive = $false
try {
  $null = Invoke-WebRequest "$base/api/health" -UseBasicParsing -TimeoutSec 3
  $alive = $true
} catch { }
if (-not $alive) {
  Write-Host "服务没在跑，先启动..."
  & (Join-Path $root "run.ps1") -Background
  Start-Sleep -Seconds 3
}

# 2. 找 Edge
$edge = (Get-Command msedge.exe -ErrorAction SilentlyContinue).Source
if (-not $edge) {
  foreach ($p in @(
      "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
      "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
    )) {
    if (Test-Path $p) { $edge = $p; break }
  }
}
if (-not $edge) {
  Write-Host "没找到 Edge。用别的浏览器打开这个地址也行：$base/widget.html"
  Start-Process "$base/widget.html"
  return
}

# 3. 开小窗（--app 去掉地址栏和标签页）
$url = "$base/widget.html"
Start-Process -FilePath $edge -ArgumentList "--app=$url", "--window-size=$Width,$Height" | Out-Null
Write-Host "已打开接话挂件：$url"

if ($NoTop) { return }

# 4. 置顶（浏览器自己做不到，借 Win32 的 SetWindowPos）
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class MeWin {
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
}
"@

$hwnd = [IntPtr]::Zero
for ($i = 0; $i -lt 24 -and $hwnd -eq [IntPtr]::Zero; $i++) {
  Start-Sleep -Milliseconds 500
  $win = Get-Process msedge -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle -like "*接话*" } |
    Select-Object -First 1
  if ($win) { $hwnd = $win.MainWindowHandle }
}

if ($hwnd -eq [IntPtr]::Zero) {
  Write-Host "窗口没找到，置顶失败。可以用 PowerToys 的 Always on Top（Win + Ctrl + T）。"
  return
}

# HWND_TOPMOST = -1；SWP_NOSIZE 0x1 | SWP_NOMOVE 0x2
$null = [MeWin]::SetWindowPos($hwnd, [IntPtr](-1), 0, 0, 0, 0, 3)
Write-Host "已置顶。想取消置顶就关掉小窗再开：.\scripts\widget.ps1 -NoTop"
