"""微信历史导入（只读）。

数据来源：本机微信 4.x 本地库，经 `wechatauto`（独立安装）只读解密。
本脚本只调用它的读接口（get_sessions / get_messages / get_nickname），
绝不调用 send / forward / labels 等会对外发消息的能力。

默认只导私聊，群聊要显式加 --include-groups（按结论：本人语料主要在私聊）。

用法（必须用工具环境的 python，见 docs/usage.md 第六节）：
    D:\agent\_tools\wechat-export\.venv\Scripts\python.exe scripts\import_wechat.py --dry-run
    ... --limit-per-chat 5000
    ... --chat wxid_xxx
    ... --include-groups --limit-per-chat 300 --min-messages 20
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# wechatauto 装在独立环境里，这里只借用它的包目录，不改项目依赖。
# pywin32 的 DLL 在 site-packages 的子目录里，靠 .pth 生效；手动加路径时要连子目录一起加。
WECHATAUTO_SP = Path(r"D:\agent\_tools\wechat-export\.venv\Lib\site-packages")
if WECHATAUTO_SP.exists():
    for sub in ("", "win32", "win32/lib", "pywin32_system32", "Pythonwin"):
        p = WECHATAUTO_SP / sub
        if p.exists():
            sys.path.insert(0, str(p))

from app.db import store  # noqa: E402
from app.config import DB_PATH  # noqa: E402

MAX_LEN = 5000
PAGE = 500
NON_TEXT = ("文件/链接/卡片", "图片", "语音", "视频", "表情", "系统", "通话", "位置", "名片", "动画")
SKIP_USERNAMES = ("brandsessionholder", "filehelper", "weixin", "fmessage", "medianote", "newsapp")
SELF_LABEL = "自己"


def is_group(username: str) -> bool:
    return username.endswith("@chatroom")


def is_official(username: str) -> bool:
    return username.startswith("gh_") or username in SKIP_USERNAMES


def resolve(db, cache: dict, username: str) -> str:
    """wxid → 备注名/昵称；拿不到就退回 wxid。群名与群成员都走这里。"""
    if not username:
        return ""
    if username in cache:
        return cache[username]
    try:
        name = db.get_nickname(username) or username
    except Exception:
        name = username
    cache[username] = name
    return name


def strip_sender_prefix(text: str, sender: str) -> str:
    """群消息正文常以「发送者:」开头（发送者是 wxid 或昵称），去掉它。

    只认两种 head：wxid_ 形式的 id，或与 sender 完全相同的一段短文字，
    避免把「data:\\n」这类正文误伤。
    """
    head, sep, rest = text.partition(":")
    if not sep or not rest or "\n" in head or len(head) > 60:
        return text
    if head.startswith("wxid_") or head == sender:
        return rest.lstrip()
    return text


def convert(msg: dict, conv: str, self_user: str, grouped: bool = False) -> dict | None:
    kind = str(msg.get("type") or "")
    text = (msg.get("content") or "").strip()
    if any(k in kind for k in NON_TEXT):
        return None
    if not text or text.startswith("<msg") or text.startswith("<?xml"):
        return None
    sender = msg.get("sender_username") or ""
    if grouped:
        text = strip_sender_prefix(text, sender).strip()
        if not text:
            return None
    if len(text) > MAX_LEN:
        return None
    if all(ch in "。，！？…~～、,.!? \n\t-" for ch in text):
        return None
    ts = datetime.fromtimestamp(int(msg["create_time"])).astimezone().replace(microsecond=0)
    return {
        "ts": ts.isoformat(),
        "text": text,
        "sender": sender,
        "is_me": 1 if sender == self_user else 0,
    }


def fetch_all(db, user: str, cap: int | None) -> list[dict]:
    out: list[dict] = []
    offset = 0
    while True:
        want = PAGE if cap is None else min(PAGE, cap - len(out))
        if want <= 0:
            break
        batch = db.get_messages(user, limit=want, offset=offset)
        if not batch:
            break
        out.extend(batch)
        offset += len(batch)
        if len(batch) < want:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="把微信聊天历史导入 me.db（只读源库）")
    ap.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    ap.add_argument("--include-groups", action="store_true", help="也导群聊（默认只导私聊）")
    ap.add_argument("--chat", action="append", default=[], help="只导指定会话（wxid / 群号），可重复")
    ap.add_argument("--limit-per-chat", type=int, default=0, help="每个会话最多导多少条，0 = 全部")
    ap.add_argument("--min-messages", type=int, default=1, help="少于这个条数的会话跳过")
    args = ap.parse_args()

    from wechatauto import WeChatDB

    db = WeChatDB()
    sessions = db.get_sessions(limit=2000)
    self_user = getattr(db, "self_username", None) or getattr(db, "wxid", None) or ""

    picked = []
    for s in sessions:
        u = s["username"]
        if args.chat:
            if u not in args.chat:
                continue
        elif is_official(u) or (is_group(u) and not args.include_groups):
            continue
        picked.append(s)

    print(f"库：{DB_PATH}")
    print(f"会话总数 {len(sessions)}，本次处理 {len(picked)} 个" + ("（含群）" if args.include_groups else "（仅私聊）"))
    if not self_user:
        print("提示：没拿到 self_username，is_me 一律按 0 处理")

    total_read = total_kept = total_dup = 0
    rows_out = []
    cache: dict[str, str] = {}
    for s in picked:
        user = s["username"]
        grouped = is_group(user)
        conv = SELF_LABEL if user == self_user else resolve(db, cache, user)
        cap = args.limit_per_chat or None
        raw = fetch_all(db, user, cap)
        rows = [r for r in (convert(m, conv, self_user, grouped) for m in raw) if r]
        if grouped:
            # 群里要看清「谁说的」：把成员 wxid 换成昵称（私聊不动，避免指纹变化重复导入）
            for r in rows:
                if not r["is_me"]:
                    r["sender"] = resolve(db, cache, r["sender"])
        if len(rows) < args.min_messages:
            continue
        total_read += len(raw)
        print(f"  {conv[:20]:<22} 读 {len(raw):>6} → 文本 {len(rows):>6}"
              f"（本人 {sum(r['is_me'] for r in rows):>5}）")
        rows_out.append((conv, rows, grouped))

    if args.dry_run:
        kept = sum(len(r) for _, r, _g in rows_out)
        print(f"\n[dry-run] 合计：读 {total_read} 条 → 可入库 {kept} 条，未写库")
        return 0

    store.init_db()
    for conv, rows, grouped in rows_out:
        # 登记会话元信息：区分人与群，人物表重建时靠它排除群名
        store.upsert_conv(conv, "wechat", 1 if grouped else 0)
        for r in rows:
            got = store.insert_message(
                r["text"], ts=r["ts"], source="wechat", conv=conv,
                sender=r["sender"], is_me=r["is_me"], kind="text",
            )
            if got:
                total_kept += 1
            else:
                total_dup += 1

    print(f"\n合计：读 {total_read} 条 → 新增 {total_kept} 条，重复跳过 {total_dup} 条")
    print(f"库内总数：{store.count_messages()} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
