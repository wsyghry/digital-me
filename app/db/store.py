"""数据层：唯一可以直接写 SQL 的地方。

对外只给几个函数：建库、写入、列表、检索、统计。
业务层要用数据，调这里；别在别的文件里拼 SQL。
"""

import hashlib
import sqlite3
from datetime import datetime
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
    """建库建表。可重复执行。"""
    with _connect() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def _fingerprint(ts: str, source: str, conv: str | None, sender: str, text: str) -> str:
    raw = "\x1f".join([ts, source, conv or "", sender, text])
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
) -> dict[str, Any] | None:
    """写入一条。指纹重复返回 None（调用方据此判断是否重复）。"""
    ts = ts or now_iso()
    created_at = now_iso()
    fp = _fingerprint(ts, source, conv, sender, text)
    conn = _connect()
    try:
        if conn.execute("SELECT 1 FROM messages WHERE fp = ?", (fp,)).fetchone():
            return None
        cur = conn.execute(
            "INSERT INTO messages (ts, source, conv, sender, is_me, text, kind, fp, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, source, conv, sender, is_me, text, kind, fp, created_at),
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
) -> list[dict[str, Any]]:
    """按 id 倒序取，keyset 分页（不用 OFFSET）；start/end 是 YYYY-MM-DD 的日期过滤。"""
    where, params = _date_clause(start, end)
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


def export_markdown() -> str:
    """把全部记录导成按日期分组的 Markdown，正文不改一字。"""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT ts, source, text FROM messages ORDER BY ts ASC, id ASC"
        ).fetchall()
    finally:
        conn.close()

    lines = ["# 分身志导出", ""]
    last_day = ""
    for r in rows:
        day = (r["ts"] or "")[:10]
        if day != last_day:
            lines += [f"## {day}", ""]
            last_day = day
        stamp = (r["ts"] or "")[11:16]
        lines += [f"**{stamp}** · {r['source']}", "", r["text"], ""]
    if len(rows) == 0:
        lines += ["（还没有记录）", ""]
    return "\n".join(lines)


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_messages(
    fts_query: str,
    short_terms: list[str],
    limit: int = 50,
    start: str | None = None,
    end: str | None = None,
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
