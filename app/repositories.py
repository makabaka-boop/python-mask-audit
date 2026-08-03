"""仓储层。

集中管理所有实体的持久化与业务校验：规则、分组、成员、样例、
演练记录、命中明细、规则快照与审计事件。SQL 全部收敛于此。
"""

import json
from datetime import datetime, timezone

from . import config
from .errors import ConflictError, NotFoundError, ValidationError


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #
def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _loads(text):
    if not text:
        return {}
    if isinstance(text, dict):
        return text
    return json.loads(text)


def rule_to_dict(row):
    return {
        "id": row["id"],
        "rule_name": row["rule_name"],
        "field_type": row["field_type"],
        "match_type": row["match_type"],
        "match_value": row["match_value"],
        "replace_strategy": row["replace_strategy"],
        "replace_config": _loads(row["replace_config"]),
        "priority": row["priority"],
        "enabled": bool(row["enabled"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def group_to_dict(row):
    return {
        "id": row["id"],
        "group_name": row["group_name"],
        "description": row["description"],
        "created_at": row["created_at"],
    }


def sample_to_dict(row):
    return {
        "id": row["id"],
        "sample_name": row["sample_name"],
        "sample_category": row["sample_category"],
        "raw_text": row["raw_text"],
        "expected_note": row["expected_note"],
        "created_at": row["created_at"],
    }


def run_to_dict(row):
    return {
        "id": row["id"],
        "sample_id": row["sample_id"],
        "rule_id": row["rule_id"],
        "group_id": row["group_id"],
        "input_text": row["input_text"],
        "output_text": row["output_text"],
        "hit_count": row["hit_count"],
        "executed_at": row["executed_at"],
    }


def hit_to_dict(row):
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "rule_id": row["rule_id"],
        "matched_count": row["matched_count"],
        "before_fragment": row["before_fragment"],
        "after_fragment": row["after_fragment"],
    }


def snapshot_to_dict(row):
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "rule_id": row["rule_id"],
        "rule_name": row["rule_name"],
        "enabled": bool(row["enabled"]),
        "priority": row["priority"],
        "match_type": row["match_type"],
        "replace_strategy": row["replace_strategy"],
        "replace_config": _loads(row["replace_config"]),
    }


# --------------------------------------------------------------------------- #
# 校验
# --------------------------------------------------------------------------- #
def _validate_rule_fields(rule_name, field_type, match_type, match_value, replace_strategy, replace_config, priority):
    if not rule_name or not str(rule_name).strip():
        raise ValidationError("rule_name 不能为空", details={"field": "rule_name"})
    if not field_type or not str(field_type).strip():
        raise ValidationError("field_type 不能为空", details={"field": "field_type"})
    if match_type not in config.MATCH_TYPES:
        raise ValidationError(
            "match_type 非法",
            details={"match_type": match_type, "allowed": list(config.MATCH_TYPES)},
        )
    if match_value is None or match_value == "":
        raise ValidationError("match_value 不能为空", details={"field": "match_value"})
    if replace_strategy not in config.REPLACE_STRATEGIES:
        raise ValidationError(
            "replace_strategy 非法",
            details={"replace_strategy": replace_strategy, "allowed": list(config.REPLACE_STRATEGIES)},
        )
    if replace_config is not None and not isinstance(replace_config, dict):
        raise ValidationError("replace_config 必须是对象", details={"field": "replace_config"})
    if priority is not None and not isinstance(priority, int):
        raise ValidationError("priority 必须是整数", details={"field": "priority"})
    # regex 入库前必须编译校验。
    if match_type == "regex":
        import re

        try:
            re.compile(match_value)
        except re.error as exc:
            raise ValidationError(
                "regex 编译失败", details={"match_value": match_value, "reason": str(exc)}
            )


# --------------------------------------------------------------------------- #
# 规则
# --------------------------------------------------------------------------- #
def create_rule(conn, payload):
    rule_name = payload.get("rule_name")
    field_type = payload.get("field_type")
    match_type = payload.get("match_type")
    match_value = payload.get("match_value")
    replace_strategy = payload.get("replace_strategy")
    replace_config = payload.get("replace_config") or {}
    priority = payload.get("priority", 100)
    enabled = payload.get("enabled", True)

    _validate_rule_fields(
        rule_name, field_type, match_type, match_value, replace_strategy, replace_config, priority
    )

    now = _now()
    cur = conn.execute(
        """INSERT INTO rules
           (rule_name, field_type, match_type, match_value, replace_strategy,
            replace_config, priority, enabled, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            rule_name,
            field_type,
            match_type,
            match_value,
            replace_strategy,
            json.dumps(replace_config, ensure_ascii=False),
            priority if priority is not None else 100,
            1 if enabled else 0,
            now,
            now,
        ),
    )
    conn.commit()
    rule = get_rule(conn, cur.lastrowid)
    write_audit(conn, "rule_created", "rule", rule["id"], {"rule_name": rule_name})
    return rule


def get_rule(conn, rule_id):
    row = conn.execute("SELECT * FROM rules WHERE id=?", (rule_id,)).fetchone()
    if row is None:
        raise NotFoundError("规则不存在", details={"rule_id": rule_id})
    return rule_to_dict(row)


def list_rules(conn):
    rows = conn.execute("SELECT * FROM rules ORDER BY priority ASC, id ASC").fetchall()
    return [rule_to_dict(r) for r in rows]


def set_rule_enabled(conn, rule_id, enabled):
    get_rule(conn, rule_id)  # 存在性校验
    conn.execute(
        "UPDATE rules SET enabled=?, updated_at=? WHERE id=?",
        (1 if enabled else 0, _now(), rule_id),
    )
    conn.commit()
    write_audit(
        conn,
        "rule_enabled" if enabled else "rule_disabled",
        "rule",
        rule_id,
        {"enabled": bool(enabled)},
    )
    return get_rule(conn, rule_id)


def update_rule_priority(conn, rule_id, priority):
    if not isinstance(priority, int):
        raise ValidationError("priority 必须是整数", details={"priority": priority})
    old = get_rule(conn, rule_id)
    conn.execute(
        "UPDATE rules SET priority=?, updated_at=? WHERE id=?",
        (priority, _now(), rule_id),
    )
    conn.commit()
    write_audit(
        conn,
        "rule_priority_changed",
        "rule",
        rule_id,
        {"from": old["priority"], "to": priority},
    )
    return get_rule(conn, rule_id)


# --------------------------------------------------------------------------- #
# 分组与成员
# --------------------------------------------------------------------------- #
def create_group(conn, payload):
    group_name = payload.get("group_name")
    description = payload.get("description") or ""
    if not group_name or not str(group_name).strip():
        raise ValidationError("group_name 不能为空", details={"field": "group_name"})
    now = _now()
    cur = conn.execute(
        "INSERT INTO groups (group_name, description, created_at) VALUES (?,?,?)",
        (group_name, description, now),
    )
    conn.commit()
    group = get_group(conn, cur.lastrowid)
    write_audit(conn, "group_created", "group", group["id"], {"group_name": group_name})
    return group


def get_group(conn, group_id):
    row = conn.execute("SELECT * FROM groups WHERE id=?", (group_id,)).fetchone()
    if row is None:
        raise NotFoundError("分组不存在", details={"group_id": group_id})
    return group_to_dict(row)


def list_groups(conn):
    rows = conn.execute("SELECT * FROM groups ORDER BY id ASC").fetchall()
    return [group_to_dict(r) for r in rows]


def add_group_member(conn, group_id, rule_id):
    get_group(conn, group_id)
    get_rule(conn, rule_id)
    exists = conn.execute(
        "SELECT 1 FROM group_members WHERE group_id=? AND rule_id=?",
        (group_id, rule_id),
    ).fetchone()
    if exists:
        raise ConflictError(
            "规则已在分组中", details={"group_id": group_id, "rule_id": rule_id}
        )
    conn.execute(
        "INSERT INTO group_members (group_id, rule_id, added_at) VALUES (?,?,?)",
        (group_id, rule_id, _now()),
    )
    conn.commit()
    write_audit(
        conn, "group_member_added", "group", group_id, {"rule_id": rule_id}
    )
    return list_group_members(conn, group_id)


def remove_group_member(conn, group_id, rule_id):
    get_group(conn, group_id)
    cur = conn.execute(
        "DELETE FROM group_members WHERE group_id=? AND rule_id=?",
        (group_id, rule_id),
    )
    conn.commit()
    if cur.rowcount == 0:
        raise NotFoundError(
            "分组成员不存在", details={"group_id": group_id, "rule_id": rule_id}
        )
    write_audit(
        conn, "group_member_removed", "group", group_id, {"rule_id": rule_id}
    )
    return list_group_members(conn, group_id)


def list_group_members(conn, group_id):
    get_group(conn, group_id)
    rows = conn.execute(
        """SELECT r.* FROM group_members gm
           JOIN rules r ON r.id = gm.rule_id
           WHERE gm.group_id=?
           ORDER BY r.priority ASC, r.id ASC""",
        (group_id,),
    ).fetchall()
    return [rule_to_dict(r) for r in rows]


def get_group_enabled_rules(conn, group_id):
    """返回分组内启用的规则，按优先级排序。禁用规则不参与演练。"""
    rows = conn.execute(
        """SELECT r.* FROM group_members gm
           JOIN rules r ON r.id = gm.rule_id
           WHERE gm.group_id=? AND r.enabled=1
           ORDER BY r.priority ASC, r.id ASC""",
        (group_id,),
    ).fetchall()
    return rows


# --------------------------------------------------------------------------- #
# 样例
# --------------------------------------------------------------------------- #
def create_sample(conn, payload):
    sample_name = payload.get("sample_name")
    sample_category = payload.get("sample_category") or ""
    raw_text = payload.get("raw_text")
    expected_note = payload.get("expected_note") or ""
    if not sample_name or not str(sample_name).strip():
        raise ValidationError("sample_name 不能为空", details={"field": "sample_name"})
    if raw_text is None:
        raise ValidationError("raw_text 不能为空", details={"field": "raw_text"})
    now = _now()
    cur = conn.execute(
        """INSERT INTO samples (sample_name, sample_category, raw_text, expected_note, created_at)
           VALUES (?,?,?,?,?)""",
        (sample_name, sample_category, raw_text, expected_note, now),
    )
    conn.commit()
    sample = get_sample(conn, cur.lastrowid)
    write_audit(conn, "sample_created", "sample", sample["id"], {"sample_name": sample_name})
    return sample


def get_sample(conn, sample_id):
    row = conn.execute("SELECT * FROM samples WHERE id=?", (sample_id,)).fetchone()
    if row is None:
        raise NotFoundError("样例不存在", details={"sample_id": sample_id})
    return sample_to_dict(row)


def list_samples(conn):
    rows = conn.execute("SELECT * FROM samples ORDER BY id ASC").fetchall()
    return [sample_to_dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# 演练记录 / 命中明细 / 快照
# --------------------------------------------------------------------------- #
def create_run(conn, *, sample_id, rule_id, group_id, input_text, output_text, hit_count, hit_details, snapshots):
    """写入演练记录、命中明细与规则快照（一次事务）。"""
    now = _now()
    cur = conn.execute(
        """INSERT INTO runs (sample_id, rule_id, group_id, input_text, output_text, hit_count, executed_at)
           VALUES (?,?,?,?,?,?,?)""",
        (sample_id, rule_id, group_id, input_text, output_text, hit_count, now),
    )
    run_id = cur.lastrowid
    for d in hit_details:
        conn.execute(
            """INSERT INTO hit_details (run_id, rule_id, matched_count, before_fragment, after_fragment)
               VALUES (?,?,?,?,?)""",
            (run_id, d["rule_id"], d["matched_count"], d["before_fragment"], d["after_fragment"]),
        )
    for s in snapshots:
        conn.execute(
            """INSERT INTO rule_snapshots
               (run_id, rule_id, rule_name, enabled, priority, match_type, replace_strategy, replace_config)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                run_id,
                s["rule_id"],
                s["rule_name"],
                1 if s["enabled"] else 0,
                s["priority"],
                s["match_type"],
                s["replace_strategy"],
                json.dumps(s["replace_config"], ensure_ascii=False),
            ),
        )
    conn.commit()
    write_audit(
        conn,
        "run_executed",
        "run",
        run_id,
        {"sample_id": sample_id, "rule_id": rule_id, "group_id": group_id, "hit_count": hit_count},
    )
    return get_run(conn, run_id)


def get_run(conn, run_id):
    row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if row is None:
        raise NotFoundError("演练记录不存在", details={"run_id": run_id})
    return run_to_dict(row)


def list_runs(conn):
    rows = conn.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
    return [run_to_dict(r) for r in rows]


def get_run_hits(conn, run_id):
    rows = conn.execute("SELECT * FROM hit_details WHERE run_id=? ORDER BY id ASC", (run_id,)).fetchall()
    return [hit_to_dict(r) for r in rows]


def get_run_snapshots(conn, run_id):
    rows = conn.execute(
        "SELECT * FROM rule_snapshots WHERE run_id=? ORDER BY priority ASC, id ASC", (run_id,)
    ).fetchall()
    return [snapshot_to_dict(r) for r in rows]


def get_run_detail(conn, run_id):
    run = get_run(conn, run_id)
    run["hit_details"] = get_run_hits(conn, run_id)
    run["rule_snapshots"] = get_run_snapshots(conn, run_id)
    return run


def rule_hit_stats(conn, rule_id):
    """统计某规则的累计命中次数与被演练次数。"""
    get_rule(conn, rule_id)
    row = conn.execute(
        """SELECT COALESCE(SUM(matched_count),0) AS total_matched,
                  COUNT(*) AS hit_records
           FROM hit_details WHERE rule_id=?""",
        (rule_id,),
    ).fetchone()
    return {
        "rule_id": rule_id,
        "total_matched": row["total_matched"],
        "hit_records": row["hit_records"],
    }


# --------------------------------------------------------------------------- #
# 审计维度查询辅助（SQL 集中在此，聚合逻辑见 audit_queries 模块）
# --------------------------------------------------------------------------- #
def rule_snapshot_versions(conn, rule_id):
    """规则在历史快照中出现过的配置版本（去重）。"""
    rows = conn.execute(
        """SELECT rule_name, enabled, priority, match_type, replace_strategy, replace_config
           FROM rule_snapshots WHERE rule_id=? ORDER BY id ASC""",
        (rule_id,),
    ).fetchall()
    versions = []
    seen = set()
    for r in rows:
        version = {
            "rule_name": r["rule_name"],
            "enabled": bool(r["enabled"]),
            "priority": r["priority"],
            "match_type": r["match_type"],
            "replace_strategy": r["replace_strategy"],
            "replace_config": _loads(r["replace_config"]),
        }
        key = json.dumps(version, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            versions.append(version)
    return versions


def rule_last_hit_time(conn, rule_id):
    """规则最近一次命中的时间（取命中所在演练记录的 executed_at）。"""
    row = conn.execute(
        """SELECT r.executed_at AS executed_at
           FROM hit_details h JOIN runs r ON r.id = h.run_id
           WHERE h.rule_id=? ORDER BY r.id DESC LIMIT 1""",
        (rule_id,),
    ).fetchone()
    return row["executed_at"] if row else None


def runs_for_sample(conn, sample_id):
    """样例的全部演练记录，按时间倒序。"""
    rows = conn.execute(
        "SELECT * FROM runs WHERE sample_id=? ORDER BY id DESC", (sample_id,)
    ).fetchall()
    return [run_to_dict(r) for r in rows]


def sample_rule_hit_distribution(conn, sample_id):
    """样例各规则的命中分布：按 rule_id 汇总命中次数与命中记录数。"""
    rows = conn.execute(
        """SELECT h.rule_id AS rule_id,
                  COALESCE(SUM(h.matched_count),0) AS total_matched,
                  COUNT(*) AS hit_records
           FROM hit_details h JOIN runs r ON r.id = h.run_id
           WHERE r.sample_id=?
           GROUP BY h.rule_id
           ORDER BY total_matched DESC, h.rule_id ASC""",
        (sample_id,),
    ).fetchall()
    return [
        {
            "rule_id": r["rule_id"],
            "total_matched": r["total_matched"],
            "hit_records": r["hit_records"],
        }
        for r in rows
    ]


def latest_regression_event_for_sample(conn, sample_id):
    """样例最近一次回归验证事件（来自审计事件）。"""
    row = conn.execute(
        """SELECT * FROM audit_events
           WHERE event_type='regression' AND entity_type='sample' AND entity_id=?
           ORDER BY id DESC LIMIT 1""",
        (sample_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "detail": _loads(row["detail"]),
        "created_at": row["created_at"],
    }


def group_runs(conn, group_id):
    """分组的全部演练记录，按时间倒序。"""
    rows = conn.execute(
        "SELECT * FROM runs WHERE group_id=? ORDER BY id DESC", (group_id,)
    ).fetchall()
    return [run_to_dict(r) for r in rows]


def group_snapshot_members_history(conn, group_id):
    """分组历史快照中出现过的成员规则（跨所有分组演练去重）。"""
    rows = conn.execute(
        """SELECT DISTINCT s.rule_id AS rule_id, s.rule_name AS rule_name
           FROM rule_snapshots s JOIN runs r ON r.id = s.run_id
           WHERE r.group_id=?
           ORDER BY s.rule_id ASC""",
        (group_id,),
    ).fetchall()
    return [{"rule_id": r["rule_id"], "rule_name": r["rule_name"]} for r in rows]


def latest_run_for_sample(conn, sample_id):
    """回归验证：定位样例最近一次演练记录。"""
    row = conn.execute(
        "SELECT * FROM runs WHERE sample_id=? ORDER BY id DESC LIMIT 1", (sample_id,)
    ).fetchone()
    if row is None:
        return None
    return run_to_dict(row)


def latest_group_run_for_sample(conn, sample_id):
    """回归验证：定位样例最近一次「使用分组」的演练记录。"""
    row = conn.execute(
        "SELECT * FROM runs WHERE sample_id=? AND group_id IS NOT NULL ORDER BY id DESC LIMIT 1",
        (sample_id,),
    ).fetchone()
    if row is None:
        return None
    return run_to_dict(row)


# --------------------------------------------------------------------------- #
# 规则冲突检测
# --------------------------------------------------------------------------- #
def detect_group_conflicts(conn, group_id):
    """检测分组内规则之间可能互相覆盖的问题。

    仅返回风险提示，不阻止保存规则、加入分组或执行演练。至少检测三类：

    * ``duplicate_exact``            —— 同一 field_type 下完全相同的 exact 规则。
    * ``contains_overlap``           —— contains 规则的匹配值互相包含。
    * ``same_priority_different_replace`` —— 优先级相同但替换策略或配置不同。
    """
    get_group(conn, group_id)
    rules = list_group_members(conn, group_id)
    conflicts = []

    n = len(rules)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = rules[i], rules[j]

            # 1) 同一 field_type 下完全相同的 exact 规则。
            if (
                a["match_type"] == "exact"
                and b["match_type"] == "exact"
                and a["field_type"] == b["field_type"]
                and a["match_value"] == b["match_value"]
            ):
                conflicts.append(
                    {
                        "rule_ids": [a["id"], b["id"]],
                        "conflict_type": "duplicate_exact",
                        "message": (
                            f"字段类型 {a['field_type']} 下存在完全相同的 exact 规则"
                            f"（match_value={a['match_value']!r}）"
                        ),
                        "severity": "high",
                    }
                )

            # 2) contains 规则的匹配值互相包含。
            if a["match_type"] == "contains" and b["match_type"] == "contains":
                av, bv = a["match_value"], b["match_value"]
                if av and bv and (av in bv or bv in av):
                    conflicts.append(
                        {
                            "rule_ids": [a["id"], b["id"]],
                            "conflict_type": "contains_overlap",
                            "message": (
                                f"contains 规则匹配值互相包含（{av!r} 与 {bv!r}），"
                                f"可能重复或互相覆盖"
                            ),
                            "severity": "medium",
                        }
                    )

            # 3) 优先级相同但替换策略或配置不同。
            if a["priority"] == b["priority"] and (
                a["replace_strategy"] != b["replace_strategy"]
                or a["replace_config"] != b["replace_config"]
            ):
                conflicts.append(
                    {
                        "rule_ids": [a["id"], b["id"]],
                        "conflict_type": "same_priority_different_replace",
                        "message": (
                            f"两条规则优先级相同（priority={a['priority']}）但替换策略或配置不同，"
                            f"执行顺序不确定可能导致结果不稳定"
                        ),
                        "severity": "medium",
                    }
                )

    write_audit(
        conn, "conflict_detected", "group", group_id, {"conflict_count": len(conflicts)}
    )
    return conflicts


# --------------------------------------------------------------------------- #
# 审计事件
# --------------------------------------------------------------------------- #
def write_audit(conn, event_type, entity_type, entity_id, detail=None):
    conn.execute(
        "INSERT INTO audit_events (event_type, entity_type, entity_id, detail, created_at) VALUES (?,?,?,?,?)",
        (event_type, entity_type, entity_id, json.dumps(detail or {}, ensure_ascii=False), _now()),
    )
    conn.commit()


def list_audit_events(conn, limit=100):
    rows = conn.execute(
        "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [
        {
            "id": r["id"],
            "event_type": r["event_type"],
            "entity_type": r["entity_type"],
            "entity_id": r["entity_id"],
            "detail": _loads(r["detail"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]
