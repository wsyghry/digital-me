-- 分身志 数据结构 · 唯一出处
-- 字段含义见 docs/data-schema.md，改这里必须同步改文档。

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT    NOT NULL,
    source     TEXT    NOT NULL DEFAULT 'note',
    conv       TEXT,
    sender     TEXT    NOT NULL DEFAULT 'me',
    is_me      INTEGER NOT NULL DEFAULT 1,
    text       TEXT    NOT NULL,
    kind       TEXT    NOT NULL DEFAULT 'text',
    ext_id     TEXT,
    fp         TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_ts     ON messages(ts);
CREATE INDEX IF NOT EXISTS idx_messages_source ON messages(source);
CREATE INDEX IF NOT EXISTS idx_messages_conv   ON messages(conv);
CREATE INDEX IF NOT EXISTS idx_messages_is_me  ON messages(is_me);
-- ext_id 的唯一索引在 store._migrate() 里建：老库要先 ALTER 补列，索引才能建

CREATE TABLE IF NOT EXISTS persons (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    aliases    TEXT,
    note       TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS convs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    source   TEXT NOT NULL,
    name     TEXT NOT NULL,
    is_group INTEGER NOT NULL DEFAULT 0,
    note     TEXT
);

-- 全文索引：external content，不重复存正文，靠下面三个触发器同步。
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    text,
    conv,
    sender,
    content     = 'messages',
    content_rowid = 'id',
    tokenize    = trigram
);

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, text, conv, sender)
    VALUES (new.id, new.text, new.conv, new.sender);
END;

CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text, conv, sender)
    VALUES ('delete', old.id, old.text, old.conv, old.sender);
END;

CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text, conv, sender)
    VALUES ('delete', old.id, old.text, old.conv, old.sender);
    INSERT INTO messages_fts(rowid, text, conv, sender)
    VALUES (new.id, new.text, new.conv, new.sender);
END;
