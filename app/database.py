"""SQLite 数据库连接与建表。"""
import sqlite3
from contextlib import contextmanager
from flask import current_app, g

from .config import Config

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name TEXT NOT NULL,
    field_type TEXT NOT NULL,
    match_type TEXT NOT NULL CHECK(match_type IN ('exact','contains','regex')),
    match_value TEXT NOT NULL,
    replace_strategy TEXT NOT NULL CHECK(replace_strategy IN ('fixed','keep_edges','middle_mask')),
    replace_config TEXT NOT NULL DEFAULT '{}',
    priority INTEGER NOT NULL DEFAULT 100,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    rule_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(group_id, rule_id),
    FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE,
    FOREIGN KEY(rule_id) REFERENCES rules(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_name TEXT NOT NULL,
    sample_category TEXT,
    raw_text TEXT NOT NULL,
    expected_note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id INTEGER,
    rule_id INTEGER,
    group_id INTEGER,
    input_text TEXT NOT NULL,
    output_text TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    executed_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(sample_id) REFERENCES samples(id) ON DELETE SET NULL,
    FOREIGN KEY(rule_id) REFERENCES rules(id) ON DELETE SET NULL,
    FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS hit_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    rule_id INTEGER,
    matched_count INTEGER NOT NULL DEFAULT 0,
    before_fragment TEXT,
    after_fragment TEXT,
    FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE,
    FOREIGN KEY(rule_id) REFERENCES rules(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS rule_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    rule_id INTEGER,
    rule_name TEXT,
    enabled INTEGER,
    priority INTEGER,
    match_type TEXT,
    match_value TEXT,
    replace_strategy TEXT,
    replace_config TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE,
    FOREIGN KEY(rule_id) REFERENCES rules(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id INTEGER,
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_group_members_group ON group_members(group_id);
CREATE INDEX IF NOT EXISTS idx_group_members_rule ON group_members(rule_id);
CREATE INDEX IF NOT EXISTS idx_runs_executed ON runs(executed_at);
CREATE INDEX IF NOT EXISTS idx_hits_run ON hit_details(run_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_run ON rule_snapshots(run_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at);
"""


def get_db() -> sqlite3.Connection:
    """获取请求范围内的数据库连接。"""
    if "db" not in g:
        conn = sqlite3.connect(
            current_app.config.get("DATABASE_PATH", Config.DATABASE_PATH)
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def db_cursor(commit: bool = False):
    db = get_db()
    cursor = db.cursor()
    try:
        yield cursor
        if commit:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        cursor.close()


def init_db(app) -> None:
    """在应用上下文中初始化数据库表。"""
    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA_SQL)
        db.commit()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
