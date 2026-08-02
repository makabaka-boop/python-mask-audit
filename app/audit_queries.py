"""审计查询模块：从规则、样例、分组三个维度追踪演练历史。

只做聚合查询，不修改任何数据。
"""

from . import repositories as repo


def rule_history(db, rule_id: int) -> dict:
    """规则维度：当前配置、历史快照配置版本、累计命中、最近命中时间。"""
    current = repo.get_rule(db, rule_id)
    stats = repo.rule_hit_stats(db, rule_id)
    return {
        "rule_id": rule_id,
        "current_config": current,
        "config_versions": repo.rule_config_versions(db, rule_id),
        "total_hits": stats["total_hits"],
        "last_hit_at": repo.rule_last_hit_at(db, rule_id),
    }


def sample_history(db, sample_id: int) -> dict:
    """样例维度：最近演练、最近回归验证结果、各规则命中分布。"""
    repo.get_sample(db, sample_id)
    latest_regression = None
    for event in repo.find_audits_by_type(db, "regression_check"):
        if event["detail"].get("sample_id") == sample_id:
            latest_regression = {
                "audited_at": event["created_at"],
                "base_run_id": event["entity_id"],
                "group_id": event["detail"].get("group_id"),
                "passed": event["detail"].get("passed"),
                "output_changed": event["detail"].get("output_changed"),
                "change_count": event["detail"].get("change_count"),
            }
            break
    return {
        "sample_id": sample_id,
        "recent_runs": repo.sample_runs(db, sample_id),
        "latest_regression": latest_regression,
        "rule_hit_distribution": repo.sample_rule_hit_distribution(db, sample_id),
    }


def group_history(db, group_id: int) -> dict:
    """分组维度：当前成员、历史快照成员、成员变化后的执行差异摘要。"""
    repo.get_group(db, group_id)
    current_members = repo.list_group_rules(db, group_id)
    snapshot_members = repo.group_snapshot_members(db, group_id)

    member_change_summary = None
    runs = repo.group_recent_runs(db, group_id, limit=2)
    if len(runs) == 2:
        latest, previous = runs[0], runs[1]
        latest_ids = {s["rule_id"] for s in repo.get_snapshot(db, latest["id"])}
        previous_ids = {s["rule_id"] for s in repo.get_snapshot(db, previous["id"])}
        same_input = latest["input_text"] == previous["input_text"]
        member_change_summary = {
            "previous_run_id": previous["id"],
            "latest_run_id": latest["id"],
            "added_rule_ids": sorted(latest_ids - previous_ids),
            "removed_rule_ids": sorted(previous_ids - latest_ids),
            "same_input": same_input,
            "previous_hit_count": previous["hit_count"],
            "latest_hit_count": latest["hit_count"],
            "previous_output_text": previous["output_text"],
            "latest_output_text": latest["output_text"],
            # 输入不同则无法直接归因输出差异
            "output_changed": (latest["output_text"] != previous["output_text"])
                              if same_input else None,
        }
    return {
        "group_id": group_id,
        "current_members": current_members,
        "snapshot_members": snapshot_members,
        "member_change_summary": member_change_summary,
    }
