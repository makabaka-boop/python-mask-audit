from __future__ import annotations
"""审计查询服务：从规则、样例、分组三个维度聚合历史数据。"""
import json

from app.repositories.audit_repo import AuditRepository
from app.repositories.group_repo import GroupRepository
from app.repositories.rule_repo import RuleRepository
from app.repositories.run_repo import RunRepository
from app.repositories.sample_repo import SampleRepository
from app.repositories.snapshot_repo import SnapshotRepository


class AuditQueryService:

    @staticmethod
    def rule_view(db, rule_id: int) -> dict:
        rule = RuleRepository.get_by_id(db, rule_id)
        if rule is None:
            return None

        current_config = rule.to_dict()

        snapshot_items = SnapshotRepository.get_items_by_rule(db, rule_id)
        config_versions = []
        seen_configs: set[str] = set()
        for item in reversed(snapshot_items):
            config_key = _config_fingerprint(item)
            if config_key in seen_configs:
                continue
            seen_configs.add(config_key)
            snapshot = SnapshotRepository.get_by_id(db, item.snapshot_id)
            config_versions.append({
                "snapshot_id": item.snapshot_id,
                "rule_id": item.rule_id,
                "rule_name": item.rule_name,
                "match_type": item.match_type,
                "match_value": item.match_value,
                "replace_strategy": item.replace_strategy,
                "replace_config": json.loads(item.replace_config) if item.replace_config else {},
                "priority": item.priority,
                "enabled": bool(item.enabled),
                "recorded_at": snapshot.created_at.isoformat() if snapshot and snapshot.created_at else None,
            })

        stats = RunRepository.get_rule_stats(db, rule_id)

        return {
            "rule_id": rule_id,
            "current_config": current_config,
            "config_versions": config_versions,
            "total_hits": stats["total_hits"],
            "last_hit_at": stats["last_run_at"],
        }

    @staticmethod
    def sample_view(db, sample_id: int) -> dict:
        sample = SampleRepository.get_by_id(db, sample_id)
        if sample is None:
            return None

        latest_run = None
        runs = RunRepository.list_by_sample(db, sample_id, limit=1)
        if runs:
            latest_run = runs[0].to_dict()
            hit_details = RunRepository.get_hit_details(db, runs[0].id)
            latest_run["hit_details"] = [h.to_dict() for h in hit_details]

        latest_regression_event = AuditRepository.get_latest_event(
            db, event_type="REGRESSION_REPLAY", target_type="group",
        )
        latest_regression = None
        if latest_regression_event:
            detail = json.loads(latest_regression_event.detail) if latest_regression_event.detail else {}
            if detail.get("sample_id") == sample_id:
                latest_regression = {
                    "event_id": latest_regression_event.id,
                    "event_type": latest_regression_event.event_type,
                    "is_consistent": detail.get("is_consistent"),
                    "diff_reasons": detail.get("diff_reasons", []),
                    "snapshot_id": detail.get("snapshot_id"),
                    "created_at": latest_regression_event.created_at.isoformat()
                    if latest_regression_event.created_at else None,
                }

        distribution_rows = RunRepository.get_hit_distribution_by_sample(db, sample_id)
        rule_hit_distribution = []
        for row in distribution_rows:
            rule = RuleRepository.get_by_id(db, row["rule_id"])
            rule_hit_distribution.append({
                "rule_id": row["rule_id"],
                "rule_name": rule.rule_name if rule else f"deleted_{row['rule_id']}",
                "total_hits": row["total_hits"],
                "hit_count": row["hit_count"],
                "last_hit_at": row["last_hit_at"],
            })

        return {
            "sample_id": sample_id,
            "sample_name": sample.sample_name,
            "latest_run": latest_run,
            "latest_regression": latest_regression,
            "rule_hit_distribution": rule_hit_distribution,
        }

    @staticmethod
    def group_view(db, group_id: int) -> dict:
        group = GroupRepository.get_by_id(db, group_id)
        if group is None:
            return None

        current_rules = GroupRepository.get_rules(db, group_id, enabled_only=False)
        current_member_ids = sorted([r.id for r in current_rules])

        snapshots = SnapshotRepository.get_snapshots_by_group(db, group_id, limit=20)
        historical_snapshots = []
        snapshot_members_map: dict[int, list[int]] = {}
        for snap in snapshots:
            items = SnapshotRepository.get_items(db, snap.id)
            member_ids = sorted([item.rule_id for item in items])
            snapshot_members_map[snap.id] = member_ids
            historical_snapshots.append({
                "snapshot_id": snap.id,
                "created_at": snap.created_at.isoformat() if snap.created_at else None,
                "rule_ids": member_ids,
                "label": snap.label or "",
            })

        member_change_diff = None
        if historical_snapshots:
            latest_snapshot = historical_snapshots[0]
            latest_snap_id = latest_snapshot["snapshot_id"]
            latest_snap_members = set(snapshot_members_map.get(latest_snap_id, []))
            current_set = set(current_member_ids)
            added = sorted(current_set - latest_snap_members)
            removed = sorted(latest_snap_members - current_set)

            execution_diff_summary = _build_execution_diff_summary(
                db, group_id, added, removed, latest_snap_id
            )

            member_change_diff = {
                "added": added,
                "removed": removed,
                "latest_snapshot_id": latest_snap_id,
                "execution_diff_summary": execution_diff_summary,
            }

        return {
            "group_id": group_id,
            "group_name": group.group_name,
            "current_members": current_member_ids,
            "historical_snapshots": historical_snapshots,
            "member_change_diff": member_change_diff,
        }


def _config_fingerprint(item) -> str:
    parts = [
        item.match_type or "",
        item.match_value or "",
        item.replace_strategy or "",
        item.replace_config or "{}",
        str(item.priority),
        str(item.enabled),
    ]
    return "|".join(parts)


def _build_execution_diff_summary(db, group_id: int, added: list[int],
                                  removed: list[int],
                                  snapshot_id: int | None) -> str:
    parts: list[str] = []
    if added:
        names = []
        for rid in added:
            rule = RuleRepository.get_by_id(db, rid)
            names.append(rule.rule_name if rule else str(rid))
        parts.append("新增规则: " + ", ".join(names))
    if removed:
        names = []
        for rid in removed:
            rule = RuleRepository.get_by_id(db, rid)
            names.append(rule.rule_name if rule else str(rid))
        parts.append("移除规则: " + ", ".join(names))
    if not added and not removed:
        runs = RunRepository.list_by_group(db, group_id, limit=1)
        if runs and runs[0].snapshot_id == snapshot_id:
            parts.append("成员无变化，最近一次演练使用当前快照，输出一致")
        else:
            parts.append("成员无变化，但最近一次演练可能使用了不同快照")
    return "；".join(parts) if parts else "无差异"
