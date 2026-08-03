"""规则快照。

在每次写入演练记录时，为参与执行的规则封存一份快照，记录规则的
ID、名称、启用状态、优先级、匹配方式、替换策略与替换配置，便于回放
每次演练所用的规则配置，并支撑回归验证。
"""

import json


def build_snapshot(rule):
    """由规则行构造快照字典。"""
    return {
        "rule_id": rule["id"],
        "rule_name": rule["rule_name"],
        "enabled": bool(rule["enabled"]),
        "priority": rule["priority"],
        "match_type": rule["match_type"],
        "replace_strategy": rule["replace_strategy"],
        "replace_config": rule["replace_config"]
        if isinstance(rule["replace_config"], dict)
        else json.loads(rule["replace_config"] or "{}"),
    }


def build_snapshots(rules):
    """为一组规则构造快照列表。"""
    return [build_snapshot(r) for r in rules]
