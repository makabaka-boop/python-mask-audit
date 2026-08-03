"""SQLite 连接与建表。

保存以下实体：脱敏规则、规则分组、分组成员、样例文本、演练记录、
命中明细、规则快照、审计事件。
"""

import sqlite3

from . import config


SCHEMA = """
CREATE TABLE IF NOT EXISTS rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name       TEXT NOT NULL,
    field_type      TEXT NOT NULL,
    match_type      TEXT NOT NULL,
    match_value     TEXT NOT NULL,
    replace_strategy TEXT NOT NULL,
    replace_config  TEXT NOT NULL DEFAULT '{}',
    priority        INTEGER NOT NULL DEFAULT 100,
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name  TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS group_members (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    rule_id  INTEGER NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE(group_id, rule_id),
    FOREIGN KEY(group_id) REFERENCES groups(id),
    FOREIGN KEY(rule_id) REFERENCES rules(id)
);

CREATE TABLE IF NOT EXISTS samples (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_name     TEXT NOT NULL,
    sample_category TEXT NOT NULL DEFAULT '',
    raw_text        TEXT NOT NULL,
    expected_note   TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id   INTEGER,
    rule_id     INTEGER,
    group_id    INTEGER,
    input_text  TEXT NOT NULL,
    output_text TEXT NOT NULL,
    hit_count   INTEGER NOT NULL DEFAULT 0,
    executed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hit_details (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER NOT NULL,
    rule_id        INTEGER NOT NULL,
    matched_count  INTEGER NOT NULL DEFAULT 0,
    before_fragment TEXT NOT NULL DEFAULT '',
    after_fragment  TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS rule_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL,
    rule_id         INTEGER NOT NULL,
    rule_name       TEXT NOT NULL,
    enabled         INTEGER NOT NULL,
    priority        INTEGER NOT NULL,
    match_type      TEXT NOT NULL,
    replace_strategy TEXT NOT NULL,
    replace_config  TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id   INTEGER,
    detail      TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL
);
"""


def get_connection(db_path=None):
    """创建一个新的 SQLite 连接（row_factory=Row，开启外键）。"""
    conn = sqlite3.connect(db_path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path=None):
    """初始化数据库表结构。"""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
