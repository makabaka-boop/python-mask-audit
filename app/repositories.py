"""仓储层：所有 SQL 访问集中在此，向上返回 dict。"""

import json
from datetime import datetime

from .errors import conflict_error, not_found


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row_to_dict(row):
    return dict(row) if row is not None else None


def rule_to_dict(row):
    d = _row_to_dict(row)
    if d:
        d["enabled"] = bool(d["enabled"])
        d["replace_config"] = json.loads(d["replace_config"] or "{}")
    return d


# ---------- 规则 ----------

def create_rule(db, fields: dict) -> dict:
    now = _now()
    try:
        cur = db.execute(
            """INSERT INTO rules (rule_name, field_type, match_type, match_value,
                                  replace_strategy, replace_config, priority, enabled,
                                  created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fields["rule_name"], fields["field_type"], fields["match_type"],
             fields["match_value"], fields["replace_strategy"], fields["replace_config"],
             fields["priority"], fields["enabled"], now, now),
        )
    except Exception as exc:
        if "UNIQUE" in str(exc):
            raise conflict_error("规则名称已存在", {"rule_name": fields["rule_name"]})
        raise
    return get_rule(db, cur.lastrowid)


def get_rule(db, rule_id: int) -> dict:
    row = db.query_one("SELECT * FROM rules WHERE id = ?", (rule_id,))
    if row is None:
        raise not_found("规则不存在", {"rule_id": rule_id})
    return rule_to_dict(row)


def list_rules(db) -> list:
    rows = db.query_all("SELECT * FROM rules ORDER BY priority DESC, id ASC")
    return [rule_to_dict(r) for r in rows]


def set_rule_enabled(db, rule_id: int, enabled: bool) -> dict:
    get_rule(db, rule_id)
    db.execute("UPDATE rules SET enabled = ?, updated_at = ? WHERE id = ?",
               (1 if enabled else 0, _now(), rule_id))
    return get_rule(db, rule_id)


def set_rule_priority(db, rule_id: int, priority: int) -> dict:
    get_rule(db, rule_id)
    db.execute("UPDATE rules SET priority = ?, updated_at = ? WHERE id = ?",
               (priority, _now(), rule_id))
    return get_rule(db, rule_id)


# ---------- 分组 ----------

def create_group(db, group_name: str, description: str) -> dict:
    try:
        cur = db.execute(
            "INSERT INTO rule_groups (group_name, description, created_at) VALUES (?, ?, ?)",
            (group_name, description, _now()),
        )
    except Exception as exc:
        if "UNIQUE" in str(exc):
            raise conflict_error("分组名称已存在", {"group_name": group_name})
        raise
    return get_group(db, cur.lastrowid)


def get_group(db, group_id: int) -> dict:
    row = db.query_one("SELECT * FROM rule_groups WHERE id = ?", (group_id,))
    if row is None:
        raise not_found("分组不存在", {"group_id": group_id})
    return _row_to_dict(row)


def list_groups(db) -> list:
    rows = db.query_all("""
        SELECT g.*, COUNT(m.id) AS rule_count
        FROM rule_groups g
        LEFT JOIN group_members m ON m.group_id = g.id
        GROUP BY g.id ORDER BY g.id ASC
    """)
    return [dict(r) for r in rows]


def add_group_rule(db, group_id: int, rule_id: int) -> dict:
    get_group(db, group_id)
    get_rule(db, rule_id)
    try:
        db.execute(
            "INSERT INTO group_members (group_id, rule_id, created_at) VALUES (?, ?, ?)",
            (group_id, rule_id, _now()),
        )
    except Exception as exc:
        if "UNIQUE" in str(exc):
            raise conflict_error("规则已在分组中", {"group_id": group_id, "rule_id": rule_id})
        raise
    return {"group_id": group_id, "rule_id": rule_id}


def remove_group_rule(db, group_id: int, rule_id: int) -> None:
    get_group(db, group_id)
    cur = db.execute("DELETE FROM group_members WHERE group_id = ? AND rule_id = ?",
                     (group_id, rule_id))
    if cur.rowcount == 0:
        raise not_found("规则不在该分组中", {"group_id": group_id, "rule_id": rule_id})


def list_group_rules(db, group_id: int, only_enabled: bool = False) -> list:
    get_group(db, group_id)
    sql = """SELECT r.* FROM rules r
             JOIN group_members m ON m.rule_id = r.id
             WHERE m.group_id = ?"""
    if only_enabled:
        sql += " AND r.enabled = 1"
    sql += " ORDER BY r.priority DESC, r.id ASC"
    return [rule_to_dict(r) for r in db.query_all(sql, (group_id,))]


# ---------- 样例 ----------

def create_sample(db, fields: dict) -> dict:
    cur = db.execute(
        """INSERT INTO samples (sample_name, sample_category, raw_text, expected_note, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (fields["sample_name"], fields.get("sample_category", ""),
         fields["raw_text"], fields.get("expected_note", ""), _now()),
    )
    return get_sample(db, cur.lastrowid)


def get_sample(db, sample_id: int) -> dict:
    row = db.query_one("SELECT * FROM samples WHERE id = ?", (sample_id,))
    if row is None:
        raise not_found("样例不存在", {"sample_id": sample_id})
    return _row_to_dict(row)


def list_samples(db) -> list:
    return [dict(r) for r in db.query_all("SELECT * FROM samples ORDER BY id ASC")]


# ---------- 演练记录 / 命中明细 / 快照 ----------

def create_run(db, sample_id, rule_id, group_id, input_text, output_text, hit_count) -> int:
    cur = db.execute(
        """INSERT INTO drill_runs (sample_id, rule_id, group_id, input_text, output_text,
                                   hit_count, executed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (sample_id, rule_id, group_id, input_text, output_text, hit_count, _now()),
    )
    return cur.lastrowid


def add_hit_detail(db, run_id: int, hit: dict) -> None:
    db.execute(
        """INSERT INTO hit_details (run_id, rule_id, matched_count, before_fragment, after_fragment)
           VALUES (?, ?, ?, ?, ?)""",
        (run_id, hit["rule_id"], hit["matched_count"],
         hit["before_fragment"], hit["after_fragment"]),
    )


def get_run(db, run_id: int) -> dict:
    row = db.query_one("SELECT * FROM drill_runs WHERE id = ?", (run_id,))
    if row is None:
        raise not_found("演练记录不存在", {"run_id": run_id})
    return _row_to_dict(row)


def list_hit_details(db, run_id: int) -> list:
    return [dict(r) for r in db.query_all(
        "SELECT * FROM hit_details WHERE run_id = ? ORDER BY id ASC", (run_id,))]


def save_snapshot(db, run_id: int, snapshot: list) -> None:
    for item in snapshot:
        db.execute(
            """INSERT INTO rule_snapshots (run_id, rule_id, rule_name, enabled, priority,
                                           match_type, match_value, replace_strategy, replace_config)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, item["rule_id"], item["rule_name"], item["enabled"], item["priority"],
             item["match_type"], item["match_value"], item["replace_strategy"],
             item["replace_config"]),
        )


def get_snapshot(db, run_id: int) -> list:
    return [dict(r) for r in db.query_all(
        "SELECT * FROM rule_snapshots WHERE run_id = ? ORDER BY id ASC", (run_id,))]


def find_latest_run(db, group_id=None, sample_id=None) -> dict:
    sql = "SELECT * FROM drill_runs WHERE 1 = 1"
    params = []
    if group_id is not None:
        sql += " AND group_id = ?"
        params.append(group_id)
    if sample_id is not None:
        sql += " AND sample_id = ?"
        params.append(sample_id)
    sql += " ORDER BY id DESC LIMIT 1"
    row = db.query_one(sql, tuple(params))
    if row is None:
        raise not_found("未找到符合条件的演练记录",
                        {"group_id": group_id, "sample_id": sample_id})
    return _row_to_dict(row)


def find_latest_group_run_for_sample(db, sample_id: int) -> dict:
    """某样例最近一次使用分组执行的演练记录。"""
    row = db.query_one(
        """SELECT * FROM drill_runs
           WHERE sample_id = ? AND group_id IS NOT NULL
           ORDER BY id DESC LIMIT 1""",
        (sample_id,),
    )
    if row is None:
        raise not_found("该样例还没有分组演练记录", {"sample_id": sample_id})
    return _row_to_dict(row)


# ---------- 统计 / 审计 ----------

def rule_hit_stats(db, rule_id: int) -> dict:
    get_rule(db, rule_id)
    row = db.query_one(
        """SELECT COUNT(*) AS run_count, COALESCE(SUM(matched_count), 0) AS total_hits
           FROM hit_details WHERE rule_id = ?""",
        (rule_id,),
    )
    return {"rule_id": rule_id, "run_count": row["run_count"],
            "total_hits": row["total_hits"]}


# ---------- 审计查询（三维度聚合） ----------

def rule_config_versions(db, rule_id: int) -> list:
    """规则在历史快照中出现过的全部配置版本。"""
    rows = db.query_all(
        """SELECT rule_name, enabled, priority, match_type, match_value,
                  replace_strategy, replace_config,
                  MIN(run_id) AS first_seen_run_id,
                  MAX(run_id) AS last_seen_run_id,
                  COUNT(DISTINCT run_id) AS run_count
           FROM rule_snapshots WHERE rule_id = ?
           GROUP BY rule_name, enabled, priority, match_type, match_value,
                    replace_strategy, replace_config
           ORDER BY first_seen_run_id ASC""",
        (rule_id,),
    )
    result = []
    for r in rows:
        d = dict(r)
        d["enabled"] = bool(d["enabled"])
        d["replace_config"] = json.loads(d["replace_config"] or "{}")
        result.append(d)
    return result


def rule_last_hit_at(db, rule_id: int):
    row = db.query_one(
        """SELECT MAX(d.executed_at) AS last_hit_at
           FROM hit_details h JOIN drill_runs d ON d.id = h.run_id
           WHERE h.rule_id = ? AND h.matched_count > 0""",
        (rule_id,),
    )
    return row["last_hit_at"]


def sample_runs(db, sample_id: int, limit: int = 10) -> list:
    return [dict(r) for r in db.query_all(
        """SELECT id AS run_id, rule_id, group_id, input_text, output_text,
                  hit_count, executed_at
           FROM drill_runs WHERE sample_id = ?
           ORDER BY id DESC LIMIT ?""",
        (sample_id, limit),
    )]


def sample_rule_hit_distribution(db, sample_id: int) -> list:
    return [dict(r) for r in db.query_all(
        """SELECT h.rule_id, s.rule_name,
                  COALESCE(SUM(h.matched_count), 0) AS total_hits,
                  COUNT(DISTINCT h.run_id) AS run_count
           FROM hit_details h
           JOIN drill_runs d ON d.id = h.run_id
           JOIN rules s ON s.id = h.rule_id
           WHERE d.sample_id = ? AND h.matched_count > 0
           GROUP BY h.rule_id ORDER BY total_hits DESC, h.rule_id ASC""",
        (sample_id,),
    )]


def group_snapshot_members(db, group_id: int) -> list:
    """历史快照中出现过的分组成员。"""
    return [dict(r) for r in db.query_all(
        """SELECT s.rule_id, s.rule_name,
                  COUNT(DISTINCT s.run_id) AS run_count,
                  MAX(s.run_id) AS last_seen_run_id
           FROM rule_snapshots s
           JOIN drill_runs d ON d.id = s.run_id
           WHERE d.group_id = ?
           GROUP BY s.rule_id ORDER BY s.rule_id ASC""",
        (group_id,),
    )]


def group_recent_runs(db, group_id: int, limit: int = 2) -> list:
    return [_row_to_dict(r) for r in db.query_all(
        "SELECT * FROM drill_runs WHERE group_id = ? ORDER BY id DESC LIMIT ?",
        (group_id, limit),
    )]


def find_audits_by_type(db, event_type: str) -> list:
    rows = db.query_all(
        "SELECT * FROM audit_events WHERE event_type = ? ORDER BY id DESC",
        (event_type,),
    )
    result = []
    for r in rows:
        d = dict(r)
        d["detail"] = json.loads(d["detail"] or "{}")
        result.append(d)
    return result


def add_audit(db, event_type: str, entity_type: str, entity_id, detail: dict) -> None:
    db.execute(
        """INSERT INTO audit_events (event_type, entity_type, entity_id, detail, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (event_type, entity_type, entity_id, json.dumps(detail, ensure_ascii=False), _now()),
    )


def list_audits(db, limit: int = 100) -> list:
    rows = db.query_all(
        "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,))
    result = []
    for r in rows:
        d = dict(r)
        d["detail"] = json.loads(d["detail"] or "{}")
        result.append(d)
    return result
