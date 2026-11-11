"""访问口令：只在设置了 ME_PASSWORD 时生效。

本机自用可以不设口令（默认空 = 不拦）。一旦上公网（P4），必须设：
否则任何拿到域名的人都能读写整库。
"""

import hashlib
import hmac
from urllib.parse import parse_qs

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import config

COOKIE = "me_auth"
PUBLIC_PATHS = ("/login", "/api/login", "/api/health", "/favicon.ico")


def enabled() -> bool:
    return bool(config.PASSWORD)


def _token() -> str:
    return hashlib.sha256(f"me-auth:{config.PASSWORD}".encode()).hexdigest()


def _ok(request: Request) -> bool:
    given = request.cookies.get(COOKIE, "")
    return hmac.compare_digest(given, _token())


LOGIN_HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>分身志 · 登录</title>
<style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#12100e;color:#e8e0d4;font:16px/1.6 system-ui,"Microsoft YaHei",sans-serif}
form{width:min(88vw,320px);display:flex;flex-direction:column;gap:14px}
h1{font-size:20px;margin:0 0 4px}
input{padding:12px 14px;border-radius:10px;border:1px solid #3a332c;background:#1b1815;color:inherit}
button{padding:12px;border:0;border-radius:10px;background:#c9a227;color:#1a1510;font-weight:600}
p{margin:0;color:#c0392b;min-height:1.4em;font-size:14px}
</style></head><body>
<form id="f">
  <h1>分身志</h1>
  <input id="p" type="password" placeholder="访问口令" autofocus autocomplete="current-password">
  <button>进入</button>
  <p id="e"></p>
</form>
<script>
document.getElementById('f').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const r = await fetch('/api/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({password: document.getElementById('p').value})
  });
  if (r.ok) location.replace('/');
  else document.getElementById('e').textContent = '口令不对';
});
</script></body></html>"""


def login_page() -> HTMLResponse:
    return HTMLResponse(LOGIN_HTML)


async def login(request: Request):
    try:
        body = await request.json()
        given = str(body.get("password", ""))
    except Exception:
        form = parse_qs((await request.body()).decode(errors="ignore"))
        given = (form.get("password") or [""])[0]

    if not enabled():
        return JSONResponse({"ok": True, "note": "未设口令"}, status_code=200)
    if not hmac.compare_digest(given, config.PASSWORD):
        return JSONResponse({"ok": False, "message": "口令不对"}, status_code=401)

    resp = JSONResponse({"ok": True})
    resp.set_cookie(COOKIE, _token(), max_age=60 * 60 * 24 * 30, httponly=True, samesite="lax")
    return resp


async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE)
    return resp


def check(request: Request):
    """返回 None 表示放行；返回 Response 表示拦下。"""
    if not enabled() or _ok(request):
        return None
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/api/login"):
        return None
    if path.startswith("/api/"):
        return JSONResponse({"detail": "需要口令，请先打开首页登录"}, status_code=401)
    return RedirectResponse("/login", status_code=303)
