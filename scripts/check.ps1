# 分身志 一键自检（只读，不改数据、不联网调模型）
# 用法：在项目根目录执行  .\scripts\check.ps1
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$fail = 0

function Line($name, $ok, $detail) {
    if ($ok) { Write-Output ("[ OK ] " + $name + "  " + $detail) }
    else { Write-Output ("[FAIL] " + $name + "  " + $detail); $script:fail = 1 }
}

Write-Output "== 1. venv =="
Line "python venv" (Test-Path $py) $py

Write-Output "== 2. unit tests (no network, no real db) =="
if (Test-Path $py) {
    Push-Location $root
    $out = & $py -m unittest discover -s tests 2>&1 | Out-String
    $code = $LASTEXITCODE
    Pop-Location
    $tail = ($out -split "`n" | Where-Object { $_ -match "Ran |OK|FAILED" }) -join " / "
    Line "unittest" ($code -eq 0) $tail.Trim()
} else {
    Line "unittest" $false "venv missing"
}

Write-Output "== 3. service (optional) =="
try {
    $h = Invoke-RestMethod "http://127.0.0.1:8000/api/health" -TimeoutSec 3
    Line "health" $true ("messages=" + $h.messages + " db=" + $h.db_bytes + "B llm=" + $h.llm)
} catch {
    Write-Output "[SKIP] health  服务没在跑，需要时执行 .\run.ps1 -Background"
}

Write-Output "== 4. files =="
foreach ($f in @("app\main.py", "app\db\store.py", "app\services\chat.py", "app\services\draft.py", "web\index.html", "run.ps1")) {
    Line $f (Test-Path (Join-Path $root $f)) ""
}

Write-Output ""
if ($fail -eq 0) { Write-Output "RESULT: PASS" } else { Write-Output "RESULT: FAIL" }
exit $fail
