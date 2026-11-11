"""分身志 · 接话浮窗（Windows 桌面小挂件）。

贴着微信窗口显示：当前在聊的人、最近几句话、两条拟好的回复。
点一下候选就复制；点「粘到输入框」把这句话粘进微信输入框——发送始终由你按。
只读数据库 + 只往输入框里粘贴，不替你按发送。

用法：
    .\\.venv\\Scripts\\python.exe scripts\\overlay.py
    .\\.venv\\Scripts\\python.exe scripts\\overlay.py --no-paste   # 只用复制，不碰微信窗口
    .\\.venv\\Scripts\\python.exe scripts\\overlay.py --api http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request

KEY = "#ff00fe"  # 这个颜色会被 Windows 抠成透明，用来做圆角
CARD = "#17181c"
EDGE = "#2c2e36"
TEXT = "#e8e8ea"
DIM = "#8d8f98"
ACCENT = "#e8c46a"
W, H = 360, 268
POLL_MS = 30000

API = "http://127.0.0.1:8000"
NO_PASTE = False


# ---------- 窗口相关（不依赖 pywin32）----------
user32 = ctypes.windll.user32


def find_wechat() -> int | None:
    """找微信主窗口：类名 Qt51514QWindowIcon 且标题像微信。"""
    found: list[int] = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        title = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, title, n + 1)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value == "Qt51514QWindowIcon" and ("微信" in title.value or "Weixin" in title.value):
            found.append(hwnd)
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)(cb), 0)
    return found[0] if found else None


def rect_of(hwnd: int) -> tuple[int, int, int, int]:
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wt.WORD),
        ("wScan", wt.WORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def press_ctrl_v() -> None:
    """给当前前台窗口发一次 Ctrl+V。"""
    inputs = []
    for vk, up in ((0x11, False), (0x56, False), (0x56, True), (0x11, True)):
        inp = INPUT(type=1)
        inp.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=2 if up else 0, time=0, dwExtraInfo=None)
        inputs.append(inp)
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    user32.SendInput(n, arr, ctypes.sizeof(INPUT))


# ---------- 取数据 ----------
def fetch(path: str, timeout: float = 40.0) -> dict | None:
    try:
        with urllib.request.urlopen(API.rstrip("/") + path, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def ago(minutes: int) -> str:
    if minutes < 1:
        return "刚刚"
    if minutes < 60:
        return f"{minutes} 分钟前"
    if minutes < 1440:
        return f"{minutes // 60} 小时前"
    return f"{minutes // 1440} 天前"


def cut(text: str, limit: int = 34) -> str:
    text = text.replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------- 界面 ----------
class Overlay:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("分身志 · 接话")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.97)
        try:
            self.root.wm_attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        self.root.configure(bg=KEY)
        self.canvas = tk.Canvas(self.root, width=W, height=H, bg=KEY, highlightthickness=0)
        self.canvas.pack()
        self.root.geometry(f"{W}x{H}+{self.root.winfo_screenwidth() - W - 40}+120")

        self.data: dict | None = None
        self.suggestions: list[str] = []
        self.picked = ""
        self.status = "正在读取…"
        self.drag: tuple[int, int] | None = None

        self.canvas.bind("<Button-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.root.bind("<Escape>", lambda _e: self.root.destroy())

        self.draw()
        self.refresh()
        self.root.after(POLL_MS, self._tick)

    # 拖动
    def _drag_start(self, event: tk.Event) -> None:
        self.drag = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag_move(self, event: tk.Event) -> None:
        if not self.drag:
            return
        self.root.geometry(f"+{event.x_root - self.drag[0]}+{event.y_root - self.drag[1]}")

    def _tick(self) -> None:
        self.refresh()
        self.root.after(POLL_MS, self._tick)

    # 数据
    def refresh(self) -> None:
        self.status = "正在想两句…"
        self.draw()
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self) -> None:
        data = fetch("/api/focus?n=6&draft=true")
        if data is None:
            data = fetch("/api/focus?n=6&draft=true", timeout=60)
        if data is None:
            self.status = "连不上本地服务（run.ps1 起了吗）"
            self.root.after(0, self.draw)
            return
        self.data = data
        self.suggestions = data.get("suggestions") or []
        self.picked = self.suggestions[0] if self.suggestions else ""
        self.status = "" if self.suggestions else ("没拟出来，点「换两句」再试" if data.get("messages") else "最近没人找你说话")
        self.root.after(0, self._place)
        self.root.after(0, self.draw)

    def _place(self) -> None:
        """把浮窗贴到微信右边缘。"""
        hwnd = find_wechat()
        if not hwnd:
            return
        left, top, right, _bottom = rect_of(hwnd)
        if right < 0 or left < -10000:
            return
        x = min(right + 8, self.root.winfo_screenwidth() - W - 8)
        y = max(top + 60, 40)
        self.root.geometry(f"+{x}+{y}")

    # 动作
    def copy(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        self.picked = text
        self.status = "已复制，去微信里 Ctrl+V"
        self.draw()

    def paste_to_wechat(self) -> None:
        if not self.picked:
            self.status = "先点一条候选"
            self.draw()
            return
        self.copy(self.picked)
        if NO_PASTE:
            self.status = "已复制（--no-paste 模式，不碰微信窗口）"
            self.draw()
            return
        hwnd = find_wechat()
        if not hwnd:
            self.status = "没找到微信窗口，已复制"
            self.draw()
            return
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.18)
        press_ctrl_v()
        self.status = "已粘进输入框，改完你自己按发送"
        self.draw()

    # 画
    def draw(self) -> None:
        c = self.canvas
        c.delete("all")
        r = 16
        x0, y0, x1, y1 = 1, 1, W - 1, H - 1
        c.create_polygon(
            x0 + r, y0, x1 - r, y0, x1, y0 + r, x1, y1 - r, x1 - r, y1,
            x0 + r, y1, x0, y1 - r, x0, y0 + r,
            smooth=True, splinesteps=24, fill=CARD, outline=EDGE, width=1,
        )

        conv = (self.data or {}).get("conv") or "还没有会话"
        when = ago((self.data or {}).get("minutes_ago", 0)) if self.data else ""
        c.create_text(18, 22, anchor="w", text=cut(conv, 18), fill=TEXT, font=("Microsoft YaHei UI", 12, "bold"))
        c.create_text(W - 18, 23, anchor="e", text=when, fill=DIM, font=("Microsoft YaHei UI", 8))
        c.create_line(16, 40, W - 16, 40, fill=EDGE)

        y = 54
        for m in ((self.data or {}).get("messages") or [])[-3:]:
            mine = m["who"] == "我"
            c.create_text(18, y, anchor="nw", text=("我：" if mine else ""), fill=ACCENT if mine else DIM,
                          font=("Microsoft YaHei UI", 8))
            c.create_text(44 if True else 18, y, anchor="nw", text=cut(m["text"], 26), fill=DIM if mine else TEXT,
                          font=("Microsoft YaHei UI", 9))
            y += 22

        c.create_line(16, 126, W - 16, 126, fill=EDGE)

        if not self.suggestions:
            c.create_text(18, 148, anchor="nw", text=self.status or "还没有候选", fill=DIM,
                          font=("Microsoft YaHei UI", 9), width=W - 36)
        for i, s in enumerate(self.suggestions[:2]):
            top = 136 + i * 44
            c.create_rectangle(14, top, W - 14, top + 36, fill="#20222a" if s == self.picked else "#1c1e25",
                               outline=ACCENT if s == self.picked else EDGE)
            c.create_text(24, top + 18, anchor="w", text=cut(s, 30), fill=TEXT, font=("Microsoft YaHei UI", 9))
            c.tag_bind(f"cand{i}", "<Button-1>", lambda _e, t=s: self.copy(t))
            c.create_rectangle(14, top, W - 14, top + 36, outline="", fill="", tags=(f"cand{i}",))

        # 底部按钮
        by = H - 30
        c.create_text(18, by, anchor="w", text="换两句", fill=ACCENT, font=("Microsoft YaHei UI", 9, "underline"))
        c.tag_bind("again", "<Button-1>", lambda _e: self.refresh())
        c.create_rectangle(12, by - 11, 66, by + 11, outline="", fill="", tags="again")

        c.create_text(96, by, anchor="w", text="粘到输入框", fill=ACCENT, font=("Microsoft YaHei UI", 9, "underline"))
        c.tag_bind("paste", "<Button-1>", lambda _e: self.paste_to_wechat())
        c.create_rectangle(90, by - 11, 180, by + 11, outline="", fill="", tags="paste")

        c.create_text(W - 18, by, anchor="e", text="关", fill=DIM, font=("Microsoft YaHei UI", 9, "underline"))
        c.tag_bind("close", "<Button-1>", lambda _e: self.root.destroy())
        c.create_rectangle(W - 34, by - 11, W - 8, by + 11, outline="", fill="", tags="close")

        if self.status and self.suggestions:
            c.create_text(18, H - 52, anchor="w", text=self.status, fill=DIM, font=("Microsoft YaHei UI", 8))

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    global API, NO_PASTE
    ap = argparse.ArgumentParser(description="分身志接话浮窗")
    ap.add_argument("--api", default=API, help="本地服务地址")
    ap.add_argument("--no-paste", action="store_true", help="只复制，不激活微信窗口")
    args = ap.parse_args()
    API = args.api
    NO_PASTE = args.no_paste
    Overlay().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
