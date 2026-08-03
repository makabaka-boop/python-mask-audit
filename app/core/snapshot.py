from __future__ import annotations
"""规则快照服务。"""
import json

from app.models.snapshot import RuleSnapshot
from app.repositories.snapshot_repo import SnapshotRepository


class SnapshotService:

    @staticmethod
    def create_snapshot(db, group_id, rules: list[dict], label: str = "") -> RuleSnapshot:
        snapshot = SnapshotRepository.create(db, group_id=group_id, label=label)
        for rule in rules:
            SnapshotRepository.add_item(
                db,
                snapshot_id=snapshot.id,
                rule_id=rule["id"],
                rule_name=rule["rule_name"],
                enabled=1 if rule.get("enabled", True) else 0,
                priority=rule.get("priority", 100),
                match_type=rule["match_type"],
                match_value=rule["match_value"],
                replace_strategy=rule["replace_strategy"],
                replace_config=json.dumps(
                    rule.get("replace_config", {}), ensure_ascii=False
                ),
            )
        return snapshot

    @staticmethod
    def compare_snapshot(db, snapshot_id: int, current_rules: list[dict]) -> dict:
        detailed = SnapshotService.compare_snapshot_detailed(
            db, snapshot_id, current_rules
        )
        return {
            "snapshot_id": snapshot_id,
            "rules_changed": [d["rule_id"] for d in detailed["rules_changed"]],
            "rules_added": detailed["rules_added"],
            "rules_removed": detailed["rules_removed"],
            "rules_unchanged": detailed["rules_unchanged"],
            "is_passed": detailed["is_passed"],
        }

    @staticmethod
    def compare_snapshot_detailed(db, snapshot_id: int,
                                  current_rules: list[dict]) -> dict:
        items = SnapshotRepository.get_items(db, snapshot_id)

        current_map = {rule["id"]: rule for rule in current_rules}
        snapshot_id_set = {item.rule_id for item in items}

        rules_changed: list[dict] = []
        rules_removed: list[int] = []
        rules_unchanged: list[int] = []

        for item in items:
            rule_id = item.rule_id
            if rule_id not in current_map:
                rules_removed.append(rule_id)
                continue

            current = current_map[rule_id]
            current_config = current.get("replace_config", {})
            if isinstance(current_config, str):
                current_config = json.loads(current_config) if current_config else {}
            snapshot_config = (
                json.loads(item.replace_config) if item.replace_config else {}
            )

            diff_fields: list[str] = []
            if item.match_type != current.get("match_type"):
                diff_fields.append("match_type")
            if item.match_value != current.get("match_value"):
                diff_fields.append("match_value")
            if item.replace_strategy != current.get("replace_strategy"):
                diff_fields.append("replace_strategy")
            if snapshot_config != current_config:
                diff_fields.append("replace_config")
            if item.priority != current.get("priority"):
                diff_fields.append("priority")
            if bool(item.enabled) != bool(current.get("enabled", False)):
                diff_fields.append("enabled")

            if diff_fields:
                rules_changed.append({
                    "rule_id": rule_id,
                    "rule_name": item.rule_name,
                    "diff_fields": diff_fields,
                })
            else:
                rules_unchanged.append(rule_id)

        rules_added = [
            rule["id"] for rule in current_rules if rule["id"] not in snapshot_id_set
        ]

        is_passed = not (rules_changed or rules_added or rules_removed)

        return {
            "snapshot_id": snapshot_id,
            "rules_changed": rules_changed,
            "rules_added": rules_added,
            "rules_removed": rules_removed,
            "rules_unchanged": rules_unchanged,
            "is_passed": is_passed,
        }

    @staticmethod
    def classify_diff_reasons(rules_changed: list[dict]) -> list[str]:
        reasons: set[str] = set()
        for change in rules_changed:
            fields = change.get("diff_fields", [])
            if "match_type" in fields or "match_value" in fields:
                reasons.add("规则配置变化（匹配方式或匹配值变更）")
            if "priority" in fields:
                reasons.add("优先级变化（执行顺序改变）")
            if "replace_strategy" in fields or "replace_config" in fields:
                reasons.add("替换配置变化（替换策略或参数变更）")
            if "enabled" in fields:
                reasons.add("启用状态变化（规则被启用或禁用）")
        return sorted(reasons)
