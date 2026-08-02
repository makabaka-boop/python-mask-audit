"""SQLite 连接与表结构初始化。"""

import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name TEXT NOT NULL UNIQUE,
    field_type TEXT NOT NULL,
    match_type TEXT NOT NULL CHECK (match_type IN ('exact', 'contains', 'regex')),
    match_value TEXT NOT NULL,
    replace_strategy TEXT NOT NULL CHECK (replace_strategy IN ('fixed', 'keep_edges', 'middle_mask')),
    replace_config TEXT NOT NULL DEFAULT '{}',
    priority INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rule_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES rule_groups(id),
    rule_id INTEGER NOT NULL REFERENCES rules(id),
    created_at TEXT NOT NULL,
    UNIQUE (group_id, rule_id)
);

CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_name TEXT NOT NULL,
    sample_category TEXT NOT NULL DEFAULT '',
    raw_text TEXT NOT NULL,
    expected_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drill_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id INTEGER REFERENCES samples(id),
    rule_id INTEGER REFERENCES rules(id),
    group_id INTEGER REFERENCES rule_groups(id),
    input_text TEXT NOT NULL,
    output_text TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    executed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hit_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES drill_runs(id),
    rule_id INTEGER NOT NULL REFERENCES rules(id),
    matched_count INTEGER NOT NULL DEFAULT 0,
    before_fragment TEXT NOT NULL DEFAULT '',
    after_fragment TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS rule_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES drill_runs(id),
    rule_id INTEGER NOT NULL,
    rule_name TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    priority INTEGER NOT NULL,
    match_type TEXT NOT NULL,
    match_value TEXT NOT NULL,
    replace_strategy TEXT NOT NULL,
    replace_config TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    detail TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
"""


class Database:
    """线程安全的 SQLite 访问入口。"""

    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()

    def init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def execute(self, sql: str, params=()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def query_one(self, sql: str, params=()):
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def query_all(self, sql: str, params=()):
        with self._lock:
            return self._conn.execute(sql, params).fetchall()
