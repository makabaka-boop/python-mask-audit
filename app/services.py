"""服务层：封装演练执行、快照比较等业务流程。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .conflict_detector import detect_conflicts
from .repositories import (
    AuditRepository,
    GroupRepository,
    RuleRepository,
    RunRepository,
    SampleRepository,
    SnapshotRepository,
)
from .rule_executor import (
    ExecutionResult,
    execute_rule_on_text,
    execute_rules_on_text,
)


class MaskService:
    def __init__(self) -> None:
        self.rules = RuleRepository()
        self.groups = GroupRepository()
        self.samples = SampleRepository()
        self.runs = RunRepository()
        self.snapshots = SnapshotRepository()
        self.audit = AuditRepository()

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------
    def execute_single_rule(
        self,
        rule_id: int,
        text: str,
        sample_id: Optional[int] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        rule = self.rules.get_by_id(rule_id)
        result = execute_rules_on_text(text, [rule])
        if persist:
            return self._persist_run(
                result=result,
                rules=[rule],
                sample_id=sample_id,
                rule_id=rule_id,
                group_id=None,
                input_text=text,
            )
        return self._build_preview_response(result, [rule])

    def execute_group(
        self,
        group_id: int,
        text: Optional[str] = None,
        sample_id: Optional[int] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        group = self.groups.get_by_id(group_id)
        rules = self.rules.list_enabled_in_group(group_id)
        input_text = text
        if sample_id is not None:
            sample = self.samples.get_by_id(sample_id)
            input_text = sample["raw_text"]
        if input_text is None:
            input_text = ""

        result = execute_rules_on_text(input_text, rules)
        if persist:
            return self._persist_run(
                result=result,
                rules=rules,
                sample_id=sample_id,
                rule_id=None,
                group_id=group_id,
                input_text=input_text,
            )
        return self._build_preview_response(result, rules)

    def execute_sample_on_group(
        self, group_id: int, sample_id: int
    ) -> Dict[str, Any]:
        return self.execute_group(
            group_id=group_id, sample_id=sample_id, persist=True
        )

    def preview_single_rule(self, rule_id: int, text: str) -> Dict[str, Any]:
        self.rules.get_by_id(rule_id)
        result = self.execute_single_rule(rule_id, text, persist=False)
        self.audit.record(
            event_type="preview_executed",
            entity_type="rule",
            entity_id=rule_id,
            detail={
                "text_length": len(text),
                "hit_count": result["hit_count"],
                "preview": True,
            },
        )
        return result

    def preview_group(
        self,
        group_id: int,
        text: str,
    ) -> Dict[str, Any]:
        self.groups.get_by_id(group_id)
        result = self.execute_group(group_id, text=text, persist=False)
        self.audit.record(
            event_type="preview_executed",
            entity_type="group",
            entity_id=group_id,
            detail={
                "text_length": len(text),
                "hit_count": result["hit_count"],
                "preview": True,
            },
        )
        return result

    # ------------------------------------------------------------------
    # 明细/快照
    # ------------------------------------------------------------------
    def get_run_detail(self, run_id: int) -> Dict[str, Any]:
        run = self.runs.get_by_id(run_id)
        hits = self.runs.list_hit_details(run_id)
        return {"run": run, "hit_details": hits}

    def get_run_snapshot(self, run_id: int) -> Dict[str, Any]:
        run = self.runs.get_by_id(run_id)
        snapshots = self.snapshots.list_by_run(run_id)
        return {"run": run, "snapshots": snapshots}

    def stats(self) -> Dict[str, Any]:
        per_rule = self.rules.count_hits_by_rule()
        total_hits = sum(int(r["hit_count"]) for r in per_rule)
        return {
            "total_hit_count": total_hits,
            "rule_stats": per_rule,
        }

    # ------------------------------------------------------------------
    # 审计聚合：规则 / 样例 / 分组 三个维度
    # ------------------------------------------------------------------
    def audit_by_rule(self, rule_id: int) -> Dict[str, Any]:
        rule = self.rules.get_by_id(rule_id)
        history = self._list_rule_config_versions(rule_id)
        hit_stats = self._rule_hit_summary(rule_id)
        recent_events = self.audit.list_by_entity("rule", rule_id, limit=20)
        return {
            "rule_id": rule_id,
            "current_config": {
                "rule_name": rule["rule_name"],
                "field_type": rule["field_type"],
                "match_type": rule["match_type"],
                "match_value": rule["match_value"],
                "replace_strategy": rule["replace_strategy"],
                "replace_config": rule["replace_config"],
                "priority": rule["priority"],
                "enabled": rule["enabled"],
                "updated_at": rule["updated_at"],
            },
            "config_versions": history,
            "total_hit_count": hit_stats["total_hit_count"],
            "run_count": hit_stats["run_count"],
            "last_hit_at": hit_stats["last_hit_at"],
            "recent_events": recent_events,
        }

    def audit_by_sample(self, sample_id: int) -> Dict[str, Any]:
        sample = self.samples.get_by_id(sample_id)
        latest_run = self.runs.latest_by_sample(sample_id)
        latest_run_detail = None
        latest_regression = None
        if latest_run is not None:
            latest_run_detail = self.get_run_detail(latest_run["id"])
            latest_regression = self.regression_check(run_id=latest_run["id"])
        hit_distribution = self._sample_rule_hit_distribution(sample_id)
        recent_events = self.audit.list_by_entity("sample", sample_id, limit=20)
        return {
            "sample_id": sample_id,
            "sample": {
                "sample_name": sample["sample_name"],
                "sample_category": sample["sample_category"],
                "raw_text": sample["raw_text"],
            },
            "latest_run": latest_run_detail["run"] if latest_run_detail else None,
            "latest_hit_details": latest_run_detail["hit_details"]
            if latest_run_detail
            else [],
            "latest_regression": latest_regression,
            "rule_hit_distribution": hit_distribution,
            "recent_events": recent_events,
        }

    def audit_by_group(self, group_id: int) -> Dict[str, Any]:
        group = self.groups.get_by_id(group_id)
        current_members = self.groups.list_rules(group_id, only_enabled=True)
        snapshots = self._list_group_snapshots(group_id)
        latest_run = self.runs.latest_by_group(group_id)
        latest_run_summary = None
        member_change_summary = self._group_member_change_summary(group_id)
        if latest_run is not None:
            latest_run_summary = self.get_run_detail(latest_run["id"])
        recent_events = self.audit.list_by_entity("group", group_id, limit=20)
        return {
            "group_id": group_id,
            "group_name": group["group_name"],
            "description": group.get("description"),
            "current_members": [
                {
                    "rule_id": r["id"],
                    "rule_name": r["rule_name"],
                    "priority": r["priority"],
                    "enabled": r["enabled"],
                    "match_type": r["match_type"],
                    "replace_strategy": r["replace_strategy"],
                }
                for r in current_members
            ],
            "snapshot_members": snapshots,
            "latest_run": latest_run_summary["run"] if latest_run_summary else None,
            "latest_hit_details": latest_run_summary["hit_details"]
            if latest_run_summary
            else [],
            "member_change_summary": member_change_summary,
            "recent_events": recent_events,
        }

    # ------------------------------------------------------------------
    # 冲突检测
    # ------------------------------------------------------------------
    def detect_group_conflicts(
        self, group_id: int, include_disabled: bool = False
    ) -> Dict[str, Any]:
        self.groups.get_by_id(group_id)
        rules = self.groups.list_rules(
            group_id, only_enabled=not include_disabled
        )
        conflicts = detect_conflicts(rules)
        return {
            "group_id": group_id,
            "rule_count": len(rules),
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
        }

    # ------------------------------------------------------------------
    # 回归验证：必须复用首轮定义的规则快照进行重放
    # ------------------------------------------------------------------
    def regression_check(
        self,
        sample_id: Optional[int] = None,
        group_id: Optional[int] = None,
        run_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        if run_id is None:
            if sample_id is not None:
                latest = self.runs.latest_by_sample(sample_id)
            elif group_id is not None:
                latest = self.runs.latest_by_group(group_id)
            else:
                latest = None
            if latest is None:
                return {
                    "has_baseline": False,
                    "message": "未找到可用的历史演练作为基线",
                    "changes": [],
                }
            run_id = latest["id"]

        run = self.runs.get_by_id(run_id)
        snapshots = self.snapshots.list_by_run(run_id)

        sample_id = sample_id or run.get("sample_id")
        group_id = group_id or run.get("group_id")

        # 重放输入优先使用当前样例文本（以样例为核心的回归）
        input_text = run["input_text"]
        if sample_id is not None:
            try:
                sample = self.samples.get_by_id(sample_id)
                input_text = sample["raw_text"]
            except Exception:
                input_text = run["input_text"]

        baseline_rules = [self._snapshot_to_rule(s) for s in snapshots]
        baseline_result = execute_rules_on_text(input_text, baseline_rules)

        current_rules: List[Dict[str, Any]] = []
        member_changes: List[Dict[str, Any]] = []
        if group_id is not None:
            current_rules = self.rules.list_enabled_in_group(group_id)
            member_changes = self._diff_membership(snapshots, current_rules)
        else:
            snapshot_rule_ids = [
                s["rule_id"] for s in snapshots if s["rule_id"] is not None
            ]
            current_rules = self.rules.list_by_ids(snapshot_rule_ids)
            current_rules = [r for r in current_rules if r.get("enabled")]

        current_result = execute_rules_on_text(input_text, current_rules)

        consistent = baseline_result.output_text == current_result.output_text

        change_categories = self._categorize_changes(
            snapshots, current_rules
        )

        snapshot_diff = self._snapshot_diff(snapshots, current_rules)

        result = {
            "has_baseline": True,
            "consistent": consistent,
            "baseline_run_id": run_id,
            "baseline_executed_at": run["executed_at"],
            "sample_id": sample_id,
            "group_id": group_id,
            "input_text": input_text,
            "baseline_output": baseline_result.output_text,
            "current_output": current_result.output_text,
            "baseline_hit_count": baseline_result.hit_count,
            "current_hit_count": current_result.hit_count,
            "change_categories": change_categories,
            "member_changes": member_changes,
            "snapshot_diff": snapshot_diff,
        }

        self.audit.record(
            event_type="regression_executed",
            entity_type="run",
            entity_id=run_id,
            detail={
                "sample_id": sample_id,
                "group_id": group_id,
                "consistent": consistent,
                "baseline_hit_count": baseline_result.hit_count,
                "current_hit_count": current_result.hit_count,
                "change_count": len(snapshot_diff),
            },
        )
        return result

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _persist_run(
        self,
        *,
        result: ExecutionResult,
        rules: List[Dict[str, Any]],
        sample_id: Optional[int],
        rule_id: Optional[int],
        group_id: Optional[int],
        input_text: str,
    ) -> Dict[str, Any]:
        run = self.runs.create(
            sample_id=sample_id,
            rule_id=rule_id,
            group_id=group_id,
            input_text=input_text,
            output_text=result.output_text,
            hit_count=result.hit_count,
        )
        for detail in result.details:
            self.runs.add_hit_detail(
                run_id=run["id"],
                rule_id=detail.rule_id,
                matched_count=detail.matched_count,
                before_fragment=detail.before_fragment,
                after_fragment=detail.after_fragment,
            )
        self.snapshots.create_for_run(run["id"], rules)
        self.audit.record(
            event_type="run_executed",
            entity_type="run",
            entity_id=run["id"],
            detail={
                "sample_id": sample_id,
                "rule_id": rule_id,
                "group_id": group_id,
                "hit_count": result.hit_count,
            },
        )
        return {
            "run": run,
            "hit_details": [
                {
                    "rule_id": d.rule_id,
                    "matched_count": d.matched_count,
                    "before_fragment": d.before_fragment,
                    "after_fragment": d.after_fragment,
                }
                for d in result.details
            ],
        }

    def _build_preview_response(
        self, result: ExecutionResult, rules: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        return {
            "output_text": result.output_text,
            "hit_count": result.hit_count,
            "hit_details": [
                {
                    "rule_id": d.rule_id,
                    "matched_count": d.matched_count,
                    "before_fragment": d.before_fragment,
                    "after_fragment": d.after_fragment,
                }
                for d in result.details
            ],
        }

    @staticmethod
    def _diff_rule(snapshot: Dict[str, Any], current: Dict[str, Any]) -> List[str]:
        fields = [
            ("rule_name", "rule_name"),
            ("enabled", "enabled"),
            ("priority", "priority"),
            ("match_type", "match_type"),
            ("match_value", "match_value"),
            ("replace_strategy", "replace_strategy"),
            ("replace_config", "replace_config"),
        ]
        diffs = []
        for snap_field, curr_field in fields:
            old_val = snapshot.get(snap_field)
            new_val = current.get(curr_field)
            if old_val != new_val:
                diffs.append(
                    f"{snap_field}: {old_val!r} -> {new_val!r}"
                )
        return diffs

    @staticmethod
    def _snapshot_to_rule(snap: Dict[str, Any]) -> Dict[str, Any]:
        """把规则快照转换为 rule_executor 可执行的规则字典。"""
        return {
            "id": snap.get("rule_id"),
            "rule_name": snap.get("rule_name"),
            "match_type": snap.get("match_type"),
            "match_value": snap.get("match_value"),
            "replace_strategy": snap.get("replace_strategy"),
            "replace_config": snap.get("replace_config") or {},
            "priority": snap.get("priority", 100),
            "enabled": bool(snap.get("enabled", True)),
        }

    @staticmethod
    def _diff_membership(
        snapshots: List[Dict[str, Any]], current_rules: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """对比快照成员与当前分组成员的增删。"""
        snap_ids = {
            s["rule_id"]: s for s in snapshots if s.get("rule_id") is not None
        }
        current_ids = {r["id"]: r for r in current_rules}

        changes: List[Dict[str, Any]] = []
        for rid, snap in snap_ids.items():
            if rid not in current_ids:
                changes.append(
                    {
                        "rule_id": rid,
                        "rule_name": snap.get("rule_name"),
                        "change": "removed",
                        "reason": "规则已从分组移除或被禁用",
                    }
                )
        for rid, rule in current_ids.items():
            if rid not in snap_ids:
                changes.append(
                    {
                        "rule_id": rid,
                        "rule_name": rule.get("rule_name"),
                        "change": "added",
                        "reason": "规则新加入分组",
                    }
                )
        return changes

    @staticmethod
    def _categorize_changes(
        snapshots: List[Dict[str, Any]], current_rules: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """将快照与当前规则的差异归因到四类：
        - rule_config_changed: 匹配方式/匹配值变化
        - priority_changed: 优先级变化
        - replace_config_changed: 替换策略或替换配置变化
        - membership_changed: 分组成员增删
        """
        snap_map = {
            s["rule_id"]: s for s in snapshots if s.get("rule_id") is not None
        }
        curr_map = {r["id"]: r for r in current_rules}

        result = {
            "rule_config_changed": [],
            "priority_changed": [],
            "replace_config_changed": [],
            "membership_changed": [],
        }

        for rid, snap in snap_map.items():
            if rid not in curr_map:
                result["membership_changed"].append(
                    {
                        "rule_id": rid,
                        "rule_name": snap.get("rule_name"),
                        "change": "removed",
                    }
                )
                continue
            curr = curr_map[rid]
            if (
                snap.get("match_type") != curr.get("match_type")
                or snap.get("match_value") != curr.get("match_value")
            ):
                result["rule_config_changed"].append(
                    {
                        "rule_id": rid,
                        "rule_name": curr.get("rule_name"),
                        "snapshot": {
                            "match_type": snap.get("match_type"),
                            "match_value": snap.get("match_value"),
                        },
                        "current": {
                            "match_type": curr.get("match_type"),
                            "match_value": curr.get("match_value"),
                        },
                    }
                )
            if snap.get("priority") != curr.get("priority"):
                result["priority_changed"].append(
                    {
                        "rule_id": rid,
                        "rule_name": curr.get("rule_name"),
                        "snapshot_priority": snap.get("priority"),
                        "current_priority": curr.get("priority"),
                    }
                )
            if (
                snap.get("replace_strategy") != curr.get("replace_strategy")
                or snap.get("replace_config") != curr.get("replace_config")
            ):
                result["replace_config_changed"].append(
                    {
                        "rule_id": rid,
                        "rule_name": curr.get("rule_name"),
                        "snapshot": {
                            "replace_strategy": snap.get("replace_strategy"),
                            "replace_config": snap.get("replace_config"),
                        },
                        "current": {
                            "replace_strategy": curr.get("replace_strategy"),
                            "replace_config": curr.get("replace_config"),
                        },
                    }
                )

        for rid, curr in curr_map.items():
            if rid not in snap_map:
                result["membership_changed"].append(
                    {
                        "rule_id": rid,
                        "rule_name": curr.get("rule_name"),
                        "change": "added",
                    }
                )

        return result

    @staticmethod
    def _snapshot_diff(
        snapshots: List[Dict[str, Any]], current_rules: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """生成每条快照规则与当前规则的字段级差异说明。"""
        snap_map = {
            s["rule_id"]: s for s in snapshots if s.get("rule_id") is not None
        }
        curr_map = {r["id"]: r for r in current_rules}
        diffs: List[Dict[str, Any]] = []
        for rid, snap in snap_map.items():
            if rid not in curr_map:
                diffs.append(
                    {
                        "rule_id": rid,
                        "rule_name": snap.get("rule_name"),
                        "change_type": "removed",
                        "differences": ["规则已不在当前分组/已禁用"],
                    }
                )
                continue
            curr = curr_map[rid]
            field_diffs = MaskService._diff_rule(snap, curr)
            if field_diffs:
                diffs.append(
                    {
                        "rule_id": rid,
                        "rule_name": curr.get("rule_name"),
                        "change_type": "modified",
                        "differences": field_diffs,
                    }
                )
        for rid, curr in curr_map.items():
            if rid not in snap_map:
                diffs.append(
                    {
                        "rule_id": rid,
                        "rule_name": curr.get("rule_name"),
                        "change_type": "added",
                        "differences": ["新增规则"],
                    }
                )
        return diffs

    # ------------------------------------------------------------------
    # 审计聚合辅助方法
    # ------------------------------------------------------------------
    @staticmethod
    def _rule_hit_summary(rule_id: int) -> Dict[str, Any]:
        from app.database import db_cursor

        with db_cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(matched_count), 0) AS total_hit_count,
                       COUNT(DISTINCT run_id) AS run_count,
                       MAX((SELECT executed_at FROM runs WHERE runs.id = hit_details.run_id)) AS last_hit_at
                FROM hit_details WHERE rule_id = ?
                """,
                (rule_id,),
            )
            row = cur.fetchone()
        return {
            "total_hit_count": row["total_hit_count"] or 0,
            "run_count": row["run_count"] or 0,
            "last_hit_at": row["last_hit_at"],
        }

    @staticmethod
    def _list_rule_config_versions(rule_id: int) -> List[Dict[str, Any]]:
        from app.database import db_cursor

        with db_cursor() as cur:
            cur.execute(
                """
                SELECT id, run_id, rule_name, match_type, match_value,
                       replace_strategy, replace_config, priority, enabled, created_at
                FROM rule_snapshots
                WHERE rule_id = ?
                ORDER BY id DESC
                """,
                (rule_id,),
            )
            rows = cur.fetchall()
        versions: List[Dict[str, Any]] = []
        for row in rows:
            versions.append(
                {
                    "snapshot_id": row["id"],
                    "run_id": row["run_id"],
                    "match_type": row["match_type"],
                    "match_value": row["match_value"],
                    "replace_strategy": row["replace_strategy"],
                    "replace_config": row["replace_config"],
                    "priority": row["priority"],
                    "enabled": bool(row["enabled"]),
                    "created_at": row["created_at"],
                }
            )
        return versions

    @staticmethod
    def _sample_rule_hit_distribution(sample_id: int) -> List[Dict[str, Any]]:
        from app.database import db_cursor

        with db_cursor() as cur:
            cur.execute(
                """
                SELECT h.rule_id,
                       (SELECT rule_name FROM rules WHERE id = h.rule_id) AS rule_name,
                       SUM(h.matched_count) AS total_hits,
                       COUNT(DISTINCT h.run_id) AS run_count
                FROM hit_details h
                INNER JOIN runs r ON r.id = h.run_id
                WHERE r.sample_id = ?
                GROUP BY h.rule_id
                ORDER BY total_hits DESC
                """,
                (sample_id,),
            )
            rows = cur.fetchall()
        return [
            {
                "rule_id": row["rule_id"],
                "rule_name": row["rule_name"],
                "total_hits": row["total_hits"] or 0,
                "run_count": row["run_count"] or 0,
            }
            for row in rows
        ]

    @staticmethod
    def _list_group_snapshots(group_id: int) -> List[Dict[str, Any]]:
        from app.database import db_cursor

        with db_cursor() as cur:
            cur.execute(
                """
                SELECT rs.run_id, rs.rule_id, rs.rule_name, rs.priority,
                       rs.match_type, rs.replace_strategy, rs.replace_config,
                       rs.enabled, r.executed_at
                FROM rule_snapshots rs
                INNER JOIN runs r ON r.id = rs.run_id
                WHERE r.group_id = ?
                ORDER BY rs.run_id DESC, rs.priority ASC, rs.id ASC
                """,
                (group_id,),
            )
            rows = cur.fetchall()
        runs: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            run_id = row["run_id"]
            if run_id not in runs:
                runs[run_id] = {
                    "run_id": run_id,
                    "executed_at": row["executed_at"],
                    "members": [],
                }
            runs[run_id]["members"].append(
                {
                    "rule_id": row["rule_id"],
                    "rule_name": row["rule_name"],
                    "priority": row["priority"],
                    "match_type": row["match_type"],
                    "replace_strategy": row["replace_strategy"],
                    "replace_config": row["replace_config"],
                    "enabled": bool(row["enabled"]),
                }
            )
        return list(runs.values())

    @staticmethod
    def _group_member_change_summary(group_id: int) -> List[Dict[str, Any]]:
        """汇总分组成员变更审计事件，输出规则级别的增删摘要。"""
        from app.database import db_cursor
        from app.repositories.base import parse_json_field

        with db_cursor() as cur:
            cur.execute(
                """
                SELECT event_type, detail, created_at
                FROM audit_events
                WHERE entity_type = 'group' AND entity_id = ?
                  AND event_type IN ('group_rule_added', 'group_rule_removed')
                ORDER BY id ASC
                """,
                (group_id,),
            )
            rows = cur.fetchall()

        summary: List[Dict[str, Any]] = []
        for row in rows:
            detail = parse_json_field(row["detail"], {})
            summary.append(
                {
                    "event_type": row["event_type"],
                    "rule_id": detail.get("rule_id"),
                    "changed_at": row["created_at"],
                }
            )
        return summary
