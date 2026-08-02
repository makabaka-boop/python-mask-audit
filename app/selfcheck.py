"""一致性自检：确认脱敏审计链路没有断点。

每项检查返回 {"check_name", "passed", "issue_count", "details"}，
details 最多保留 20 条问题明细，只读不写。
"""

import re

MAX_DETAILS = 20


def _check_orphan_hit_details(db) -> dict:
    """孤立命中明细：run_id 或 rule_id 已不存在。"""
    rows = db.query_all(
        """SELECT h.id, h.run_id, h.rule_id,
                  CASE WHEN d.id IS NULL THEN 'run_missing' ELSE 'rule_missing' END AS reason
           FROM hit_details h
           LEFT JOIN drill_runs d ON d.id = h.run_id
           LEFT JOIN rules r ON r.id = h.rule_id
           WHERE d.id IS NULL OR r.id IS NULL"""
    )
    return _result("orphan_hit_details", [dict(r) for r in rows])


def _check_group_runs_missing_snapshot(db) -> dict:
    """缺失快照的分组演练：分组演练必须封存规则快照才能回放。"""
    rows = db.query_all(
        """SELECT d.id AS run_id, d.group_id, d.executed_at
           FROM drill_runs d
           LEFT JOIN rule_snapshots s ON s.run_id = d.id
           WHERE d.group_id IS NOT NULL AND s.id IS NULL"""
    )
    return _result("group_run_missing_snapshot", [dict(r) for r in rows])


def _check_snapshot_hit_mismatch(db) -> dict:
    """规则快照与命中明细无法对应：命中明细的规则必须出现在该次演练快照中。"""
    rows = db.query_all(
        """SELECT h.id, h.run_id, h.rule_id
           FROM hit_details h
           LEFT JOIN rule_snapshots s
             ON s.run_id = h.run_id AND s.rule_id = h.rule_id
           WHERE s.id IS NULL"""
    )
    return _result("snapshot_hit_mismatch", [dict(r) for r in rows])


def _check_preview_residue(db) -> dict:
    """预览数据误落库：演练记录必须归属单条规则或某个分组，不允许悬空。"""
    rows = db.query_all(
        """SELECT id AS run_id, executed_at
           FROM drill_runs WHERE rule_id IS NULL AND group_id IS NULL"""
    )
    return _result("preview_residue_in_runs", [dict(r) for r in rows])


def _check_disabled_rule_participation(db) -> dict:
    """禁用规则参与演练：快照中标记为禁用的规则不应产生命中。"""
    rows = db.query_all(
        """SELECT DISTINCT h.run_id, h.rule_id, s.rule_name
           FROM hit_details h
           JOIN rule_snapshots s
             ON s.run_id = h.run_id AND s.rule_id = h.rule_id
           WHERE s.enabled = 0 AND h.matched_count > 0"""
    )
    return _result("disabled_rule_participation", [dict(r) for r in rows])


def _check_invalid_regex_residue(db) -> dict:
    """非法正则残留：绕过校验直接写入的 regex 规则必须能编译。"""
    issues = []
    rows = db.query_all(
        "SELECT id, rule_name, match_value FROM rules WHERE match_type = 'regex'"
    )
    for r in rows:
        try:
            re.compile(r["match_value"])
        except re.error as exc:
            issues.append({"rule_id": r["id"], "rule_name": r["rule_name"],
                           "match_value": r["match_value"], "regex_error": str(exc)})
    return _result("invalid_regex_residue", issues)


def _check_regression_missing_baseline(db) -> dict:
    """回归验证缺少历史基准：回归审计引用的基准演练记录必须存在。"""
    rows = db.query_all(
        """SELECT a.id AS audit_id, a.entity_id AS base_run_id, a.created_at
           FROM audit_events a
           LEFT JOIN drill_runs d ON d.id = a.entity_id
           WHERE a.event_type = 'regression_check' AND d.id IS NULL"""
    )
    return _result("regression_missing_baseline", [dict(r) for r in rows])


def _result(check_name: str, issues: list) -> dict:
    return {
        "check_name": check_name,
        "passed": len(issues) == 0,
        "issue_count": len(issues),
        "details": issues[:MAX_DETAILS],
    }


CHECKS = (
    _check_orphan_hit_details,
    _check_group_runs_missing_snapshot,
    _check_snapshot_hit_mismatch,
    _check_preview_residue,
    _check_disabled_rule_participation,
    _check_invalid_regex_residue,
    _check_regression_missing_baseline,
)


def run_selfcheck(db) -> dict:
    checks = [check(db) for check in CHECKS]
    return {
        "passed": all(c["passed"] for c in checks),
        "check_count": len(checks),
        "failed_count": sum(1 for c in checks if not c["passed"]),
        "checks": checks,
    }
