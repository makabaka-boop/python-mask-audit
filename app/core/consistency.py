from __future__ import annotations
"""一致性自检服务：检查脱敏审计链路的断点。"""
import re

from sqlalchemy import text

from app.models import (
    HitDetail,
    Rule,
    RuleSnapshot,
    RunRecord,
    SnapshotItem,
)


class ConsistencyChecker:

    @staticmethod
    def run_all_checks(db) -> dict:
        checks = [
            ConsistencyChecker._check_orphan_hit_details(db),
            ConsistencyChecker._check_group_run_missing_snapshot(db),
            ConsistencyChecker._check_snapshot_hit_mismatch(db),
            ConsistencyChecker._check_preview_data_leaked(db),
            ConsistencyChecker._check_disabled_rule_in_run(db),
            ConsistencyChecker._check_invalid_regex_residual(db),
            ConsistencyChecker._check_regression_missing_baseline(db),
        ]
        total_issues = sum(c["issue_count"] for c in checks)
        all_passed = all(c["passed"] for c in checks)
        return {
            "all_passed": all_passed,
            "total_issues": total_issues,
            "checks": checks,
        }

    @staticmethod
    def _make_check(name: str, passed: bool, issue_count: int,
                    details: list) -> dict:
        return {
            "check_name": name,
            "passed": passed,
            "issue_count": issue_count,
            "details": details,
        }

    @staticmethod
    def _check_orphan_hit_details(db) -> dict:
        rows = db.execute(
            text(
                "SELECT hd.id, hd.run_id FROM hit_details hd "
                "LEFT JOIN run_records rr ON hd.run_id = rr.id "
                "WHERE rr.id IS NULL"
            )
        ).fetchall()
        details = [
            {"hit_detail_id": r[0], "run_id": r[1]} for r in rows
        ]
        return ConsistencyChecker._make_check(
            "orphan_hit_details",
            passed=len(rows) == 0,
            issue_count=len(rows),
            details=details,
        )

    @staticmethod
    def _check_group_run_missing_snapshot(db) -> dict:
        rows = (
            db.query(RunRecord)
            .filter(RunRecord.group_id.isnot(None))
            .filter(RunRecord.snapshot_id.is_(None))
            .all()
        )
        details = [
            {"run_id": r.id, "group_id": r.group_id,
             "executed_at": r.executed_at.isoformat() if r.executed_at else None}
            for r in rows
        ]
        return ConsistencyChecker._make_check(
            "group_run_missing_snapshot",
            passed=len(rows) == 0,
            issue_count=len(rows),
            details=details,
        )

    @staticmethod
    def _check_snapshot_hit_mismatch(db) -> dict:
        issues: list[dict] = []
        runs_with_snapshots = (
            db.query(RunRecord)
            .filter(RunRecord.snapshot_id.isnot(None))
            .filter(RunRecord.group_id.isnot(None))
            .all()
        )
        for run in runs_with_snapshots:
            snapshot_items = (
                db.query(SnapshotItem)
                .filter(SnapshotItem.snapshot_id == run.snapshot_id)
                .all()
            )
            if not snapshot_items:
                issues.append({
                    "run_id": run.id,
                    "snapshot_id": run.snapshot_id,
                    "reason": "快照中没有任何规则条目",
                })
                continue

            snapshot_rule_ids = {item.rule_id for item in snapshot_items
                                 if bool(item.enabled)}
            hit_details = (
                db.query(HitDetail)
                .filter(HitDetail.run_id == run.id)
                .all()
            )
            for hd in hit_details:
                if hd.rule_id is not None and hd.rule_id not in snapshot_rule_ids:
                    snapshot_all_ids = {item.rule_id for item in snapshot_items}
                    if hd.rule_id in snapshot_all_ids:
                        issues.append({
                            "run_id": run.id,
                            "snapshot_id": run.snapshot_id,
                            "rule_id": hd.rule_id,
                            "reason": "规则在快照中为禁用状态，但产生了命中明细",
                        })
                    else:
                        issues.append({
                            "run_id": run.id,
                            "snapshot_id": run.snapshot_id,
                            "rule_id": hd.rule_id,
                            "reason": "命中明细中的规则不在快照范围内",
                        })

        return ConsistencyChecker._make_check(
            "snapshot_hit_mismatch",
            passed=len(issues) == 0,
            issue_count=len(issues),
            details=issues,
        )

    @staticmethod
    def _check_preview_data_leaked(db) -> dict:
        issues: list[dict] = []

        anomalous_runs = (
            db.query(RunRecord)
            .filter(RunRecord.rule_id.is_(None))
            .filter(RunRecord.group_id.is_(None))
            .all()
        )
        for run in anomalous_runs:
            issues.append({
                "run_id": run.id,
                "reason": "演练记录既无 rule_id 也无 group_id，数据来源不明",
            })

        inconsistent_hits = (
            db.query(HitDetail)
            .filter(HitDetail.matched_count == 0)
            .all()
        )
        for hd in inconsistent_hits:
            issues.append({
                "hit_detail_id": hd.id,
                "run_id": hd.run_id,
                "reason": "命中明细 matched_count=0 但仍被写入，可能是预览数据误落库",
            })

        return ConsistencyChecker._make_check(
            "preview_data_leaked",
            passed=len(issues) == 0,
            issue_count=len(issues),
            details=issues,
        )

    @staticmethod
    def _check_disabled_rule_in_run(db) -> dict:
        issues: list[dict] = []

        rows = db.execute(
            text(
                "SELECT hd.id, hd.run_id, hd.rule_id, r.rule_name, r.enabled "
                "FROM hit_details hd "
                "JOIN rules r ON hd.rule_id = r.id "
                "WHERE r.enabled = 0"
            )
        ).fetchall()

        for row in rows:
            run = db.query(RunRecord).filter(RunRecord.id == row[1]).first()
            if run and run.snapshot_id:
                snap_item = (
                    db.query(SnapshotItem)
                    .filter(
                        SnapshotItem.snapshot_id == run.snapshot_id,
                        SnapshotItem.rule_id == row[2],
                    )
                    .first()
                )
                if snap_item and not bool(snap_item.enabled):
                    continue
            issues.append({
                "hit_detail_id": row[0],
                "run_id": row[1],
                "rule_id": row[2],
                "rule_name": row[3],
                "reason": "当前已禁用的规则在演练中产生了命中明细",
            })

        return ConsistencyChecker._make_check(
            "disabled_rule_in_run",
            passed=len(issues) == 0,
            issue_count=len(issues),
            details=issues,
        )

    @staticmethod
    def _check_invalid_regex_residual(db) -> dict:
        issues: list[dict] = []
        rules = db.query(Rule).filter(Rule.match_type == "regex").all()
        for rule in rules:
            try:
                re.compile(rule.match_value)
            except re.error as exc:
                issues.append({
                    "rule_id": rule.id,
                    "rule_name": rule.rule_name,
                    "match_value": rule.match_value,
                    "reason": f"正则表达式编译失败: {exc}",
                })
        return ConsistencyChecker._make_check(
            "invalid_regex_residual",
            passed=len(issues) == 0,
            issue_count=len(issues),
            details=issues,
        )

    @staticmethod
    def _check_regression_missing_baseline(db) -> dict:
        issues: list[dict] = []

        groups_with_runs = (
            db.query(RunRecord.group_id)
            .filter(RunRecord.group_id.isnot(None))
            .distinct()
            .all()
        )
        for (group_id,) in groups_with_runs:
            snapshot = (
                db.query(RuleSnapshot)
                .filter(RuleSnapshot.group_id == group_id)
                .first()
            )
            if snapshot is None:
                issues.append({
                    "group_id": group_id,
                    "reason": "分组存在演练记录但没有任何快照，无法进行回归验证",
                })

        return ConsistencyChecker._make_check(
            "regression_missing_baseline",
            passed=len(issues) == 0,
            issue_count=len(issues),
            details=issues,
        )
