"""规则冲突检测：识别分组内可能互相覆盖的规则。

只返回风险提示，不阻止保存规则、加入分组或执行演练。
"""

import json
from collections import defaultdict


def _config_signature(rule) -> str:
    config = rule["replace_config"]
    if isinstance(config, str):
        config = json.loads(config or "{}")
    return json.dumps(config or {}, sort_keys=True, ensure_ascii=False)


def detect_conflicts(rules) -> list:
    """检测三类冲突，返回 [{rule_ids, conflict_type, message, severity}]。"""
    conflicts = []

    # 1. 同一 field_type 下完全相同的 exact 规则
    exact_groups = defaultdict(list)
    for r in rules:
        if r["match_type"] == "exact":
            exact_groups[(r["field_type"], r["match_value"])].append(r)
    for (field_type, match_value), group in exact_groups.items():
        if len(group) > 1:
            conflicts.append({
                "rule_ids": sorted(r["id"] for r in group),
                "conflict_type": "duplicate_exact",
                "message": (f"field_type={field_type} 下存在 {len(group)} 条完全相同的 "
                            f"exact 规则（match_value={match_value!r}），会重复覆盖同一文本"),
                "severity": "high",
            })

    # 2. contains 规则互相包含（一方的 match_value 是另一方的子串）
    contains_rules = [r for r in rules if r["match_type"] == "contains"]
    for i, a in enumerate(contains_rules):
        for b in contains_rules[i + 1:]:
            if a["match_value"] == b["match_value"]:
                continue
            if a["match_value"] in b["match_value"] or b["match_value"] in a["match_value"]:
                shorter, longer = (a, b) if len(a["match_value"]) <= len(b["match_value"]) else (b, a)
                conflicts.append({
                    "rule_ids": sorted([a["id"], b["id"]]),
                    "conflict_type": "contains_overlap",
                    "message": (f"contains 规则 {shorter['id']}（{shorter['match_value']!r}）的匹配范围 "
                                f"覆盖规则 {longer['id']}（{longer['match_value']!r}），执行顺序会影响结果"),
                    "severity": "medium",
                })

    # 3. 优先级相同但替换策略或替换配置不同
    by_priority = defaultdict(list)
    for r in rules:
        by_priority[r["priority"]].append(r)
    for priority, group in by_priority.items():
        if len(group) < 2:
            continue
        signatures = {(r["replace_strategy"], _config_signature(r)) for r in group}
        if len(signatures) > 1:
            conflicts.append({
                "rule_ids": sorted(r["id"] for r in group),
                "conflict_type": "same_priority_different_replace",
                "message": (f"{len(group)} 条规则共享优先级 {priority}，但替换策略或替换配置不同，"
                            "同优先级按规则 ID 顺序执行，结果可能不符合预期"),
                "severity": "low",
            })

    return conflicts
