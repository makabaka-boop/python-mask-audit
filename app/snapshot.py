"""规则快照：演练时封存参与执行的规则配置，支持回归对比。"""

import json

SNAPSHOT_FIELDS = ("rule_id", "rule_name", "enabled", "priority",
                   "match_type", "match_value", "replace_strategy", "replace_config")


def _serialize_config(value) -> str:
    if isinstance(value, str):
        return value or "{}"
    return json.dumps(value or {}, ensure_ascii=False)


def build_snapshot(rules) -> list:
    """把规则行转换为快照记录。"""
    snapshot = []
    for r in rules:
        snapshot.append({
            "rule_id": r["id"],
            "rule_name": r["rule_name"],
            "enabled": int(r["enabled"]),
            "priority": int(r["priority"]),
            "match_type": r["match_type"],
            "match_value": r["match_value"],
            "replace_strategy": r["replace_strategy"],
            "replace_config": _serialize_config(r["replace_config"]),
        })
    return snapshot


def _normalize_config(value):
    if isinstance(value, str):
        return json.loads(value or "{}")
    return value or {}


def diff_rules(snapshot_rows, current_rules) -> list:
    """对比历史快照与当前规则，返回变化列表。"""
    current_by_id = {r["id"]: r for r in current_rules}
    changes = []

    for snap in snapshot_rows:
        rule_id = snap["rule_id"]
        current = current_by_id.pop(rule_id, None)
        if current is None:
            changes.append({"rule_id": rule_id, "rule_name": snap["rule_name"],
                            "change_type": "deleted"})
            continue
        field_changes = {}
        pairs = [
            ("rule_name", snap["rule_name"], current["rule_name"]),
            ("enabled", int(snap["enabled"]), int(current["enabled"])),
            ("priority", int(snap["priority"]), int(current["priority"])),
            ("match_type", snap["match_type"], current["match_type"]),
            ("match_value", snap["match_value"], current["match_value"]),
            ("replace_strategy", snap["replace_strategy"], current["replace_strategy"]),
            ("replace_config",
             _normalize_config(snap["replace_config"]),
             _normalize_config(current["replace_config"])),
        ]
        for field, old, new in pairs:
            if old != new:
                field_changes[field] = {"before": old, "after": new}
        if field_changes:
            changes.append({"rule_id": rule_id, "rule_name": current["rule_name"],
                            "change_type": "modified", "field_changes": field_changes})

    for rule in current_by_id.values():
        changes.append({"rule_id": rule["id"], "rule_name": rule["rule_name"],
                        "change_type": "added"})
    return changes


# 快照字段 -> 差异来源分类
_FIELD_TO_SOURCE = {
    "priority": "priority_change",
    "replace_config": "replace_config_change",
    "rule_name": "rule_config_change",
    "match_type": "rule_config_change",
    "match_value": "rule_config_change",
    "replace_strategy": "rule_config_change",
    "enabled": "rule_config_change",
}

_SOURCE_MESSAGES = {
    "member_change": "分组成员变化：有规则被加入或移出分组执行范围",
    "priority_change": "优先级变化：规则执行顺序发生改变",
    "replace_config_change": "替换配置变化：replace_config 被修改",
    "rule_config_change": "规则配置变化：匹配方式/匹配值/替换策略/启用状态被修改",
}


def classify_changes(changes) -> list:
    """把 diff_rules 的结果归因为差异来源列表。

    来源类型：member_change / priority_change / replace_config_change / rule_config_change
    """
    sources = {}
    for change in changes:
        if change["change_type"] in ("added", "deleted"):
            fields = {"member_change"}
        else:
            fields = {_FIELD_TO_SOURCE[f] for f in change["field_changes"]}
        for source in fields:
            entry = sources.setdefault(source, {"rule_ids": set(), "rule_names": set()})
            entry["rule_ids"].add(change["rule_id"])
            entry["rule_names"].add(change["rule_name"])

    return [
        {"source": source,
         "rule_ids": sorted(entry["rule_ids"]),
         "message": f"{_SOURCE_MESSAGES[source]}（涉及规则：{'、'.join(sorted(entry['rule_names']))}）"}
        for source, entry in sorted(sources.items())
    ]
