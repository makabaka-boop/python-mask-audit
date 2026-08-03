"""脱敏审计链路一致性自检。

检查项：
1. orphan_hit_details      —— 命中明细引用了不存在的演练
2. group_run_without_snapshot —— 分组演练没有对应规则快照
3. snapshot_hit_mismatch   —— 规则快照与命中明细的 rule_id 无法对应
4. preview_persisted       —— 预览数据误写入 runs / hit_details
5. disabled_rule_in_run    —— 禁用规则参与了演练（快照中 enabled=false）
6. invalid_regex_residue   —— 规则表中残留无法编译的正则
7. regression_no_baseline  —— 回归验证缺少历史基准（样例/分组从未演练过）
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .database import db_cursor
from .repositories.base import parse_json_field, row_to_dict, rows_to_list


def _check(name: str, passed: bool, issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "issue_count": len(issues),
        "details": issues,
    }


def run_all_checks() -> Dict[str, Any]:
    checks = [
        _check_orphan_hit_details(),
        _check_group_run_without_snapshot(),
        _check_snapshot_hit_mismatch(),
        _check_preview_persisted(),
        _check_disabled_rule_in_run(),
        _check_invalid_regex_residue(),
        _check_regression_no_baseline(),
    ]
    total_issues = sum(c["issue_count"] for c in checks)
    all_passed = all(c["passed"] for c in checks)
    return {
        "status": "ok" if all_passed else "issues_found",
        "all_passed": all_passed,
        "total_issue_count": total_issues,
        "checks": checks,
    }


# ---------------------------------------------------------------------
# 1. 孤立命中明细：hit_details.run_id 指向不存在的 runs.id
# ---------------------------------------------------------------------
def _check_orphan_hit_details() -> Dict[str, Any]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT h.id AS hit_id, h.run_id, h.rule_id, h.matched_count
            FROM hit_details h
            LEFT JOIN runs r ON r.id = h.run_id
            WHERE r.id IS NULL
            """
        )
        rows = cur.fetchall()
    issues = rows_to_list(rows)
    return _check("orphan_hit_details", len(issues) == 0, issues)


# ---------------------------------------------------------------------
# 2. 分组演练缺失快照：runs.group_id NOT NULL 但没有 rule_snapshots
# ---------------------------------------------------------------------
def _check_group_run_without_snapshot() -> Dict[str, Any]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT r.id AS run_id, r.group_id, r.sample_id, r.executed_at
            FROM runs r
            LEFT JOIN rule_snapshots s ON s.run_id = r.id
            WHERE r.group_id IS NOT NULL
            GROUP BY r.id
            HAVING COUNT(s.id) = 0
            """
        )
        rows = cur.fetchall()
    issues = rows_to_list(rows)
    return _check("group_run_without_snapshot", len(issues) == 0, issues)


# ---------------------------------------------------------------------
# 3. 快照与命中明细无法对应
#    同一个 run_id 下，hit_details.rule_id 不在 rule_snapshots.rule_id 中
# ---------------------------------------------------------------------
def _check_snapshot_hit_mismatch() -> Dict[str, Any]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT h.id AS hit_id, h.run_id, h.rule_id
            FROM hit_details h
            WHERE h.rule_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM rule_snapshots s
                  WHERE s.run_id = h.run_id AND s.rule_id = h.rule_id
              )
            """
        )
        rows = cur.fetchall()
    issues = rows_to_list(rows)
    return _check("snapshot_hit_mismatch", len(issues) == 0, issues)


# ---------------------------------------------------------------------
# 4. 预览数据误落库：审计事件显示是 preview，但 runs 中存在对应记录
#    预览接口不会写 runs，所以若 audit 中 preview 事件数远大于 runs 数，
#    这里检查是否存在与 preview 同时间窗口落库的 runs（兜底防护）。
#    严格判定：runs 中没有任何记录的 input_text 与 preview audit 的 detail 相同。
# ---------------------------------------------------------------------
def _check_preview_persisted() -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, event_type, entity_type, entity_id, detail, created_at
            FROM audit_events
            WHERE event_type = 'preview_executed'
            """
        )
        preview_events = cur.fetchall()
        for event in preview_events:
            detail = parse_json_field(event["detail"], {})
            if not detail.get("preview"):
                continue
            entity_type = event["entity_type"]
            entity_id = event["entity_id"]
            if entity_type == "rule":
                cur.execute(
                    """
                    SELECT id FROM runs
                    WHERE rule_id = ?
                      AND (sample_id IS NULL AND group_id IS NULL)
                    LIMIT 1
                    """,
                    (entity_id,),
                )
                row = cur.fetchone()
                if row:
                    issues.append(
                        {
                            "audit_event_id": event["id"],
                            "entity_type": entity_type,
                            "entity_id": entity_id,
                            "run_id": row["id"],
                            "reason": "单规则预览疑似写入了 runs 表",
                        }
                    )
    return _check("preview_persisted", len(issues) == 0, issues)


# ---------------------------------------------------------------------
# 5. 禁用规则参与演练：rule_snapshots.enabled = 0
# ---------------------------------------------------------------------
def _check_disabled_rule_in_run() -> Dict[str, Any]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT s.id AS snapshot_id, s.run_id, s.rule_id, s.rule_name,
                   s.enabled, r.executed_at
            FROM rule_snapshots s
            INNER JOIN runs r ON r.id = s.run_id
            WHERE s.enabled = 0
            """
        )
        rows = cur.fetchall()
    issues = rows_to_list(rows)
    return _check("disabled_rule_in_run", len(issues) == 0, issues)


# ---------------------------------------------------------------------
# 6. 非法正则残留：rules.match_type='regex' 但 match_value 无法编译
# ---------------------------------------------------------------------
def _check_invalid_regex_residue() -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, rule_name, match_value FROM rules WHERE match_type = 'regex'"
        )
        rows = cur.fetchall()
    for row in rows:
        try:
            re.compile(row["match_value"])
        except re.error as exc:
            issues.append(
                {
                    "rule_id": row["id"],
                    "rule_name": row["rule_name"],
                    "match_value": row["match_value"],
                    "error": str(exc),
                }
            )
    return _check("invalid_regex_residue", len(issues) == 0, issues)


# ---------------------------------------------------------------------
# 7. 回归验证缺少历史基准：存在样例或分组，但从未产生过演练记录
# ---------------------------------------------------------------------
def _check_regression_no_baseline() -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT s.id AS sample_id, s.sample_name
            FROM samples s
            LEFT JOIN runs r ON r.sample_id = s.id
            WHERE r.id IS NULL
            """
        )
        for row in cur.fetchall():
            issues.append(
                {
                    "entity_type": "sample",
                    "entity_id": row["sample_id"],
                    "name": row["sample_name"],
                    "reason": "样例没有任何演练记录，无法回归",
                }
            )
        cur.execute(
            """
            SELECT g.id AS group_id, g.group_name
            FROM groups g
            LEFT JOIN runs r ON r.group_id = g.id
            WHERE r.id IS NULL
            """
        )
        for row in cur.fetchall():
            issues.append(
                {
                    "entity_type": "group",
                    "entity_id": row["group_id"],
                    "name": row["group_name"],
                    "reason": "分组没有任何演练记录，无法回归",
                }
            )
    return _check("regression_no_baseline", len(issues) == 0, issues)
