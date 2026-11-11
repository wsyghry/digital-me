"""数据层：唯一可以直接写 SQL 的地方。

对外只给几个函数：建库、写入、列表、检索、统计。
业务层要用数据，调这里；别在别的文件里拼 SQL。
"""

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from ..config import DB_PATH, SCHEMA_PATH

FIELDS = "id, ts, source, conv, sender, is_me, text, kind, created_at"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """建库建表。可重复执行；老库会自动补新增的列。"""
    with _connect() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """老库补列：schema.sql 里的 CREATE TABLE IF NOT EXISTS 不会改已有表。"""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(messages)").fetchall()}
    if "ext_id" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN ext_id TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_ext"
        " ON messages(source, ext_id) WHERE ext_id IS NOT NULL"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS aliases ("
        " name TEXT PRIMARY KEY,"
        " person TEXT NOT NULL,"
        " created_at TEXT NOT NULL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_aliases_person ON aliases(person)")


def _fingerprint(
    ts: str, source: str, conv: str | None, sender: str, text: str, ext_id: str | None = None
) -> str:
    raw = "\x1f".join([ts, source, conv or "", sender, text, ext_id or ""])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _row(r: sqlite3.Row) -> dict[str, Any]:
    return dict(r)


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def insert_message(
    text: str,
    *,
    ts: str | None = None,
    source: str = "note",
    conv: str | None = None,
    sender: str = "me",
    is_me: int = 1,
    kind: str = "text",
    ext_id: str | None = None,
) -> dict[str, Any] | None:
    """写入一条，重复返回 None。

    去重规则：给了 ext_id（导入源的原始 id）就按 (source, ext_id) 判重，
    这时同一秒同文的第二条不会被误当重复；没给就退回指纹判重。
    """
    ts = ts or now_iso()
    created_at = now_iso()
    fp = _fingerprint(ts, source, conv, sender, text, ext_id)
    legacy_fp = _fingerprint(ts, source, conv, sender, text)
    conn = _connect()
    try:
        if ext_id:
            dup = conn.execute(
                "SELECT 1 FROM messages WHERE source = ? AND ext_id = ?", (source, ext_id)
            ).fetchone()
            if dup:
                return None
            # 老库补 ext_id：上一版导入的行没有 ext_id，指纹按旧算法能对上
            old = conn.execute(
                "SELECT id FROM messages WHERE source = ? AND fp = ? AND ext_id IS NULL",
                (source, legacy_fp),
            ).fetchone()
            if old:
                conn.execute(
                    "UPDATE messages SET ext_id = ?, fp = ? WHERE id = ?", (ext_id, fp, old["id"])
                )
                conn.commit()
                return None
        else:
            dup = conn.execute("SELECT 1 FROM messages WHERE fp = ?", (fp,)).fetchone()
            if dup:
                return None
        cur = conn.execute(
            "INSERT INTO messages (ts, source, conv, sender, is_me, text, kind, ext_id, fp, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, source, conv, sender, is_me, text, kind, ext_id, fp, created_at),
        )
        conn.commit()
        row = conn.execute(f"SELECT {FIELDS} FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row(row) if row else None
    finally:
        conn.close()


def _date_clause(
    start: str | None, end: str | None, col: str = "ts"
) -> tuple[str, list[Any]]:
    """日期过滤的 SQL 片段。ts 是带时区的 ISO 串，前 10 位就是本地日期。"""
    lo = (start or "").strip()
    hi = (end or "").strip()
    if lo and hi and lo > hi:
        lo, hi = hi, lo
    if lo and hi and lo == hi:
        return f" AND substr({col}, 1, 10) = ?", [lo]
    if lo and hi:
        return f" AND substr({col}, 1, 10) BETWEEN ? AND ?", [lo, hi]
    if lo:
        return f" AND substr({col}, 1, 10) >= ?", [lo]
    if hi:
        return f" AND substr({col}, 1, 10) <= ?", [hi]
    return "", []


def list_messages(
    limit: int = 50,
    before_id: int | None = None,
    start: str | None = None,
    end: str | None = None,
    person: str | None = None,
) -> list[dict[str, Any]]:
    """按 id 倒序取，keyset 分页（不用 OFFSET）；start/end 是 YYYY-MM-DD 的日期过滤。"""
    where, params = _date_clause(start, end)
    if person:
        clause, p_args = _person_clause(person)
        where += clause
        params += p_args
    conn = _connect()
    try:
        sql = f"SELECT {FIELDS} FROM messages WHERE 1 = 1{where}"
        args: list[Any] = list(params)
        if before_id:
            sql += " AND id < ?"
            args.append(before_id)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return [_row(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def update_message(msg_id: int, text: str) -> dict[str, Any] | None:
    """改正文，指纹跟着重算。找不到返回 None，撞上别的记录会抛 IntegrityError。"""
    conn = _connect()
    try:
        row = conn.execute(f"SELECT {FIELDS} FROM messages WHERE id = ?", (msg_id,)).fetchone()
        if row is None:
            return None
        old = _row(row)
        fp = _fingerprint(old["ts"], old["source"], old["conv"], old["sender"], text)
        conn.execute("UPDATE messages SET text = ?, fp = ? WHERE id = ?", (text, fp, msg_id))
        conn.commit()
        row = conn.execute(f"SELECT {FIELDS} FROM messages WHERE id = ?", (msg_id,)).fetchone()
        return _row(row) if row else None
    finally:
        conn.close()


def delete_message(msg_id: int) -> bool:
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM messages WHERE id = ?", (msg_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def export_markdown(
    start: str | None = None, end: str | None = None, person: str | None = None
) -> str:
    """把记录导成按日期分组的 Markdown，正文不改一字；可按日期/人筛选。"""
    where, params = _date_clause(start, end)
    if person:
        clause, p_args = _person_clause(person)
        where += clause
        params += p_args
    conn = _connect()
    try:
        rows = conn.execute(
            f"SELECT ts, source, conv, sender, text FROM messages WHERE 1 = 1{where}"
            " ORDER BY ts ASC, id ASC",
            params,
        ).fetchall()
    finally:
        conn.close()

    title = "分身志导出"
    if person:
        title += f" · 与 {person}"
    if start or end:
        title += f" · {start or ''}~{end or ''}"
    lines = [f"# {title}", ""]
    last_day = ""
    for r in rows:
        day = (r["ts"] or "")[:10]
        if day != last_day:
            lines += [f"## {day}", ""]
            last_day = day
        stamp = (r["ts"] or "")[11:16]
        who = ""
        if person and r["conv"] and r["conv"] != person:
            who = f" · {r['conv']}"
        elif person and r["sender"] != person:
            who = f" · {r['sender']}"
        lines += [f"**{stamp}** · {r['source']}{who}", "", r["text"], ""]
    if len(rows) == 0:
        lines += ["（这个范围里没有记录）", ""]
    return "\n".join(lines)


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_messages(
    fts_query: str,
    short_terms: list[str],
    limit: int = 50,
    start: str | None = None,
    end: str | None = None,
    person: str | None = None,
) -> list[dict[str, Any]]:
    """两路检索：够了 3 字的词走 FTS5，短词用 LIKE 兜底或再筛；可按日期范围过滤。"""
    sql = ""
    params: list[Any] = []

    if fts_query:
        sql = (
            "SELECT m.* FROM messages m JOIN messages_fts f ON f.rowid = m.id"
            " WHERE messages_fts MATCH ?"
        )
        params.append(fts_query)
    else:
        sql = "SELECT m.* FROM messages m WHERE 1 = 1"

    for term in short_terms:
        sql += " AND m.text LIKE ? ESCAPE '\\'"
        params.append(f"%{_escape_like(term)}%")

    where, date_params = _date_clause(start, end, col="m.ts")
    sql += where
    params.extend(date_params)

    if person:
        clause, p_args = _person_clause(person, prefix="m.")
        sql += clause
        params += p_args

    sql += " ORDER BY m.ts DESC, m.id DESC LIMIT ?"
    params.append(limit)

    conn = _connect()
    try:
        return [_row(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def search_any(terms: list[str], limit: int = 200) -> list[dict[str, Any]]:
    """OR 兜底：任一片段命中就算候选，排序交给调用方（问答场景用）。"""
    if not terms:
        return []
    where = " OR ".join(["text LIKE ? ESCAPE '\\'"] * len(terms))
    sql = (
        f"SELECT {FIELDS} FROM messages WHERE {where}"
        " ORDER BY ts DESC, id DESC LIMIT ?"
    )
    params: list[Any] = [f"%{_escape_like(t)}%" for t in terms] + [limit]

    conn = _connect()
    try:
        return [_row(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def topic_segment(
    msg_id: int, minutes: int = 30, max_msgs: int = 12
) -> list[dict[str, Any]]:
    """取一条消息所属的「话题段」：同会话、时间相近的一串消息。

    用来给问答补上下文，避免只拿到半句话（比如「那就周三吧」不知道周三指什么）。
    """
    conn = _connect()
    try:
        row = conn.execute(f"SELECT {FIELDS} FROM messages WHERE id = ?", (msg_id,)).fetchone()
        if row is None:
            return []
        anchor = _row(row)
        try:
            t = datetime.fromisoformat(anchor["ts"])
        except ValueError:
            return [anchor]
        lo = (t - timedelta(minutes=minutes)).isoformat(timespec="seconds")
        hi = (t + timedelta(minutes=minutes)).isoformat(timespec="seconds")
        rows = conn.execute(
            f"SELECT {FIELDS} FROM messages WHERE conv IS ? AND ts BETWEEN ? AND ?"
            " ORDER BY ts ASC, id ASC LIMIT ?",
            (anchor["conv"], lo, hi, max_msgs),
        ).fetchall()
        return [_row(r) for r in rows] or [anchor]
    finally:
        conn.close()


def count_messages() -> int:
    conn = _connect()
    try:
        return int(conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0])
    finally:
        conn.close()


def days(limit: int = 120) -> list[dict[str, Any]]:
    """按日期汇总：哪天有多少条记录，供界面做日期索引。"""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT substr(ts, 1, 10) AS day, COUNT(*) AS n FROM messages"
            " GROUP BY day ORDER BY day DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [{"day": r["day"], "count": r["n"]} for r in rows]


def db_size_bytes() -> int:
    return DB_PATH.stat().st_size if DB_PATH.exists() else 0


def upsert_conv(name: str, source: str = "wechat", is_group: int = 0) -> None:
    """登记会话元信息（导入时调用），用来区分「人」和「群」。"""
    if not name:
        return
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, is_group FROM convs WHERE source = ? AND name = ?", (source, name)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO convs (source, name, is_group) VALUES (?, ?, ?)",
                (source, name, is_group),
            )
        elif int(row["is_group"]) != int(is_group):
            conn.execute("UPDATE convs SET is_group = ? WHERE id = ?", (is_group, row["id"]))
        conn.commit()
    finally:
        conn.close()


def group_names() -> set[str]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT name FROM convs WHERE is_group = 1").fetchall()
    finally:
        conn.close()
    return {r["name"] for r in rows}


def alias_map() -> dict[str, str]:
    """别名 → 正名。同一个人有多个昵称/备注时，用这张表归到一个人。"""
    conn = _connect()
    try:
        rows = conn.execute("SELECT name, person FROM aliases").fetchall()
    finally:
        conn.close()
    return {r["name"]: r["person"] for r in rows}


def resolve_person(name: str, mapping: dict[str, str] | None = None) -> str:
    """顺着别名链往上找正名，最多 5 跳，防环。"""
    mapping = alias_map() if mapping is None else mapping
    seen = {name}
    cur = name
    for _ in range(5):
        nxt = mapping.get(cur)
        if not nxt or nxt in seen:
            break
        seen.add(nxt)
        cur = nxt
    return cur


def person_names(person: str) -> list[str]:
    """一个人的全部名字：正名 + 所有指向它的别名。"""
    mapping = alias_map()
    names = {person}
    for name in mapping:
        if resolve_person(name, mapping) == person:
            names.add(name)
    return sorted(names)


def _person_clause(person: str, prefix: str = "") -> tuple[str, list[Any]]:
    """按人筛消息：把他的别名也算进来。"""
    names = person_names(person)
    marks = ",".join("?" * len(names))
    return (
        f" AND ({prefix}conv IN ({marks}) OR {prefix}sender IN ({marks}))",
        names + names,
    )


def set_alias(name: str, person: str) -> dict[str, Any]:
    """把 name 并到 person 名下。会成环时报错。"""
    name, person = (name or "").strip(), (person or "").strip()
    if not name or not person:
        raise ValueError("两个名字都要填")
    if name == person:
        raise ValueError("不用把一个人并到自己")
    if resolve_person(person) == name:
        raise ValueError(f"「{person}」已经并到「{name}」名下，反着再并会绕成圈")
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO aliases (name, person, created_at) VALUES (?, ?, ?)"
            " ON CONFLICT(name) DO UPDATE SET person = excluded.person",
            (name, person, now_iso()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"name": name, "person": person}


def delete_alias(name: str) -> bool:
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM aliases WHERE name = ?", (name,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_aliases() -> list[dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT name, person, created_at FROM aliases ORDER BY person, name"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def rebuild_persons() -> dict[str, int]:
    """从已有消息里归纳出「人」：私聊的会话名 + 群里发过言的昵称。

    一人一行，名字就是显示名。可重复执行，每次整表重建；别名表不受影响。
    """
    conn = _connect()
    try:
        names: dict[str, set[str]] = {}
        groups = group_names()
        for r in conn.execute(
            "SELECT DISTINCT conv FROM messages"
            " WHERE conv IS NOT NULL AND conv != '' AND conv != '自己'"
        ).fetchall():
            n = r["conv"]
            if n.endswith("@chatroom") or n.startswith("wxid_") or n in groups:
                continue
            names.setdefault(n, set()).add(n)
        for r in conn.execute(
            "SELECT DISTINCT sender FROM messages"
            " WHERE is_me = 0 AND sender NOT LIKE 'wxid_%'"
            " AND sender NOT LIKE '%@chatroom' AND sender != 'me'"
        ).fetchall():
            n = r["sender"]
            if n:
                names.setdefault(n, set()).add(n)

        conn.execute("DELETE FROM persons")
        now = now_iso()
        for name, aliases in names.items():
            conn.execute(
                "INSERT INTO persons (name, aliases, created_at) VALUES (?, ?, ?)",
                (name, json.dumps(sorted(aliases), ensure_ascii=False), now),
            )
        conn.commit()
    finally:
        conn.close()
    return {"persons": len(names)}


def list_persons(limit: int = 300) -> list[dict[str, Any]]:
    """人名 + 往来条数（私聊按会话名算，群聊按发言人算），按条数倒序。"""
    conn = _connect()
    try:
        counts: dict[str, int] = {}
        for r in conn.execute(
            "SELECT conv AS k, COUNT(*) AS n FROM messages"
            " WHERE conv IS NOT NULL AND conv != '' GROUP BY conv"
        ).fetchall():
            counts[r["k"]] = counts.get(r["k"], 0) + int(r["n"])
        for r in conn.execute(
            "SELECT sender AS k, COUNT(*) AS n FROM messages"
            " WHERE is_me = 0 GROUP BY sender"
        ).fetchall():
            counts[r["k"]] = counts.get(r["k"], 0) + int(r["n"])
        rows = conn.execute("SELECT id, name FROM persons").fetchall()
    finally:
        conn.close()

    mapping = alias_map()
    merged: dict[str, int] = {}
    for name, n in counts.items():
        key = resolve_person(name, mapping)
        merged[key] = merged.get(key, 0) + n
    ids = {r["name"]: r["id"] for r in rows}
    valid = {resolve_person(r["name"], mapping) for r in rows}
    out = [
        {"id": ids.get(name, 0), "name": name, "count": n}
        for name, n in merged.items()
        if n > 0 and name in valid
    ]
    out.sort(key=lambda x: (-x["count"], x["name"]))
    return out[:limit]

_BRACKETED = re.compile(r"[（(][^）)]{0,16}[）)]")
_NOT_NAME_CHARS = re.compile(r"[\s\W_]+", re.UNICODE)


def norm_name(name: str) -> str:
    """把名字压成可比较的形状：去括号备注、去符号与 emoji、忽略大小写。"""
    s = _BRACKETED.sub("", name or "")
    s = _NOT_NAME_CHARS.sub("", s)
    return s.lower()


def suggest_aliases(limit: int = 100) -> list[dict[str, Any]]:
    """找出「看着是同一个人」的候选，交给前端一键合并。

    只做保守规则：去掉括号备注与符号后完全相同，才建议合并。
    宁可漏，不误并——误并会让两个人混成一个，比漏并严重。
    """
    people = list_persons(limit=5000)
    buckets: dict[str, list[dict[str, Any]]] = {}
    for p in people:
        key = norm_name(p["name"])
        if key:
            buckets.setdefault(key, []).append(p)

    out: list[dict[str, Any]] = []
    for key, group in buckets.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda x: (-x["count"], len(x["name"])))
        target = group[0]
        for other in group[1:]:
            if other["count"] <= 0 or other["name"] == target["name"]:
                continue
            out.append(
                {
                    "name": other["name"],
                    "person": target["name"],
                    "count": other["count"],
                    "person_count": target["count"],
                    "reason": "去掉括号与符号后同名",
                }
            )
    out.sort(key=lambda x: (-(x["count"] + x["person_count"]), x["name"]))
    return out[:limit]


def sample_by_scene(limit_each: int = 4) -> dict[str, list[str]]:
    """按长度分档挑我自己的话当语气样本：短回复 / 日常 / 长一点。"""
    buckets = {
        "short": ("length(text) <= 12", limit_each + 1),
        "mid": ("length(text) >= 13 AND length(text) <= 40", limit_each),
        "long": ("length(text) >= 41 AND length(text) <= 120", max(limit_each - 1, 2)),
    }
    out: dict[str, list[str]] = {}
    conn = _connect()
    try:
        for key, (cond, n) in buckets.items():
            rows = conn.execute(
                "SELECT text FROM messages WHERE is_me = 1 AND kind = 'text'"
                f" AND {cond} ORDER BY id DESC LIMIT ?",
                (n,),
            ).fetchall()
            out[key] = [
                r["text"].replace("\r", " ").replace("\n", " ").strip() for r in rows
            ]
    finally:
        conn.close()
    return out


def sample_my_messages(limit: int = 10, max_chars: int = 60) -> list[str]:
    """挑几条我自己写过的短句当语气样本。

    故意不随机：固定取最近的几条，提示词前缀才稳定，能命中 DeepSeek 的缓存价。
    """
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT text FROM messages WHERE is_me = 1 AND kind = 'text'"
            " AND length(text) <= ? ORDER BY id DESC LIMIT ?",
            (max_chars, limit),
        ).fetchall()
    finally:
        conn.close()
    return [r["text"].replace("\n", " ").strip() for r in rows]


_INBOX_NOISE = ("朋友验证", "好友验证", "现在我们可以开始聊天了", "以上是打招呼的内容")


def pending_replies(
    minutes: int = 2,
    limit: int = 30,
    active_days: int = 90,
    include_groups: bool = False,
    max_chars: int = 120,
) -> list[dict[str, Any]]:
    """谁在等我回话：会话最后一条是对方发的，且已经过去 minutes 分钟。

    只读，不发消息。群聊默认不算（太吵），要算就传 include_groups=True。
    """
    minutes = max(0, int(minutes))
    now = datetime.now().astimezone()
    cutoff_new = (now - timedelta(minutes=minutes)).replace(microsecond=0).isoformat()
    since = (now - timedelta(days=max(1, int(active_days)))).replace(microsecond=0).isoformat()
    groups = set() if include_groups else group_names()

    conn = _connect()
    try:
        rows = conn.execute(
            "WITH last AS ("
            "  SELECT conv, MAX(id) AS id FROM messages"
            "  WHERE conv IS NOT NULL AND conv <> '自己' AND kind = 'text' AND ts >= ?"
            "  GROUP BY conv"
            ")"
            " SELECT m.id, m.conv, m.sender, m.ts, m.text"
            " FROM messages m JOIN last ON m.id = last.id"
            " WHERE m.is_me = 0 AND m.ts <= ?"
            " ORDER BY m.ts DESC LIMIT ?",
            (since, cutoff_new, limit * 3),
        ).fetchall()
    finally:
        conn.close()

    out: list[dict[str, Any]] = []
    for r in rows:
        if r["conv"] in groups:
            continue
        try:
            ago = int((now - datetime.fromisoformat(r["ts"])).total_seconds() // 60)
        except ValueError:
            ago = 0
        text = (r["text"] or "").replace("\r", " ").replace("\n", " ").strip()
        if any(noise in text for noise in _INBOX_NOISE):
            continue
        out.append(
            {
                "conv": r["conv"],
                "sender": r["sender"],
                "ts": r["ts"],
                "minutes_ago": ago,
                "text": text[:max_chars] + ("…" if len(text) > max_chars else ""),
            }
        )
        if len(out) >= limit:
            break
    return out

