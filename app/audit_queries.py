"""审计查询模块。

从 **规则 / 样例 / 分组** 三个维度聚合演练历史，供数据治理负责人追踪：

* 规则维度：当前配置、历史快照中出现过的配置版本、累计命中次数、最近一次命中时间。
* 样例维度：最近演练、最近回归验证结果、各规则命中分布。
* 分组维度：当前成员、历史快照成员、成员变化后的执行差异摘要。

本模块只做读侧聚合，所有 SQL 收敛在 :mod:`app.repositories`。
"""

from . import repositories as repo


def rule_audit(conn, rule_id):
    """规则维度审计视图。"""
    current = repo.get_rule(conn, rule_id)  # 不存在会抛 NotFoundError
    stats = repo.rule_hit_stats(conn, rule_id)
    return {
        "dimension": "rule",
        "rule_id": rule_id,
        "current_config": current,
        "history_versions": repo.rule_snapshot_versions(conn, rule_id),
        "total_matched": stats["total_matched"],
        "hit_records": stats["hit_records"],
        "last_hit_at": repo.rule_last_hit_time(conn, rule_id),
    }


def sample_audit(conn, sample_id):
    """样例维度审计视图。"""
    sample = repo.get_sample(conn, sample_id)
    runs = repo.runs_for_sample(conn, sample_id)
    latest_run = runs[0] if runs else None
    return {
        "dimension": "sample",
        "sample_id": sample_id,
        "sample": sample,
        "run_count": len(runs),
        "latest_run": latest_run,
        "latest_regression": repo.latest_regression_event_for_sample(conn, sample_id),
        "rule_hit_distribution": repo.sample_rule_hit_distribution(conn, sample_id),
    }


def group_audit(conn, group_id):
    """分组维度审计视图，含成员变化后的执行差异摘要。"""
    group = repo.get_group(conn, group_id)
    current_members = repo.list_group_members(conn, group_id)
    current_member_ids = [m["id"] for m in current_members]
    history_members = repo.group_snapshot_members_history(conn, group_id)
    history_member_ids = [m["rule_id"] for m in history_members]

    runs = repo.group_runs(conn, group_id)
    return {
        "dimension": "group",
        "group_id": group_id,
        "group": group,
        "current_members": current_members,
        "history_members": history_members,
        "member_change_summary": _member_change_summary(
            conn, current_member_ids, set(history_member_ids), runs
        ),
    }


def _member_change_summary(conn, current_member_ids, history_member_ids, runs):
    """按分组演练时间线，汇总相邻两次演练间的成员变化及执行差异。"""
    current_set = set(current_member_ids)

    # 相对历史快照成员集合，当前成员的增减。
    added_now = sorted(current_set - history_member_ids)
    removed_now = sorted(history_member_ids - current_set)

    # 逐次演练之间的成员与输出差异（runs 已按时间倒序，反转为正序时间线）。
    timeline = list(reversed(runs))
    transitions = []
    for prev, curr in zip(timeline, timeline[1:]):
        prev_members = {s["rule_id"] for s in repo.get_run_snapshots(conn, prev["id"])}
        curr_members = {s["rule_id"] for s in repo.get_run_snapshots(conn, curr["id"])}
        added = sorted(curr_members - prev_members)
        removed = sorted(prev_members - curr_members)
        if added or removed or prev["output_text"] != curr["output_text"]:
            transitions.append(
                {
                    "from_run_id": prev["id"],
                    "to_run_id": curr["id"],
                    "added_rule_ids": added,
                    "removed_rule_ids": removed,
                    "output_changed": prev["output_text"] != curr["output_text"],
                    "from_output": prev["output_text"],
                    "to_output": curr["output_text"],
                    "from_hit_count": prev["hit_count"],
                    "to_hit_count": curr["hit_count"],
                }
            )

    return {
        "added_vs_history": added_now,
        "removed_vs_history": removed_now,
        "run_transitions": transitions,
    }
