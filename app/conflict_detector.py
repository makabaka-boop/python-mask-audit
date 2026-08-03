"""规则冲突检测。

只返回风险提示，不阻止规则保存、加入分组或执行演练。

检测三类问题（同一 field_type 下）：
1. duplicate_exact       —— 完全相同的 exact 规则；
2. contains_overlap      —— contains 规则之间存在包含关系；
3. same_priority_diff    —— 优先级相同但替换策略/配置不同。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List


SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"


def detect_conflicts(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """对一组规则进行冲突检测，返回冲突列表。

    每条冲突结构：
    {
        "rule_ids": [1, 2],
        "conflict_type": "duplicate_exact",
        "message": "...",
        "severity": "high"
    }
    """
    conflicts: List[Dict[str, Any]] = []

    by_field: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for rule in rules:
        by_field[rule.get("field_type") or ""].append(rule)

    for _field_type, field_rules in by_field.items():
        conflicts.extend(_detect_duplicate_exact(field_rules))
        conflicts.extend(_detect_contains_overlap(field_rules))
        conflicts.extend(_detect_same_priority_diff(field_rules))

    return conflicts


def _detect_duplicate_exact(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    buckets: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for r in rules:
        if r.get("match_type") == "exact":
            buckets[r.get("match_value")].append(r)

    results = []
    for match_value, group in buckets.items():
        if len(group) >= 2:
            results.append(
                {
                    "rule_ids": sorted(r["id"] for r in group if r.get("id") is not None),
                    "conflict_type": "duplicate_exact",
                    "message": (
                        f"存在 {len(group)} 条 exact 规则匹配相同的值 "
                        f"{match_value!r}，执行结果取决于优先级与先后顺序"
                    ),
                    "severity": SEVERITY_HIGH,
                    "field_type": group[0].get("field_type"),
                    "match_value": match_value,
                }
            )
    return results


def _detect_contains_overlap(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    contains_rules = [
        r for r in rules if r.get("match_type") == "contains" and r.get("match_value")
    ]
    results = []
    seen_pairs = set()
    for i, a in enumerate(contains_rules):
        for b in contains_rules[i + 1 :]:
            va = a["match_value"]
            vb = b["match_value"]
            if va == vb:
                continue
            if va in vb:
                outer, inner = b, a
            elif vb in va:
                outer, inner = a, b
            else:
                continue
            pair = tuple(sorted([outer["id"], inner["id"]]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            results.append(
                {
                    "rule_ids": sorted(
                        rid for rid in (outer["id"], inner["id"]) if rid is not None
                    ),
                    "conflict_type": "contains_overlap",
                    "message": (
                        f"contains 规则 {outer.get('rule_name')}({outer['id']}) "
                        f"的匹配值 {outer['match_value']!r} 包含规则 "
                        f"{inner.get('rule_name')}({inner['id']}) 的匹配值 "
                        f"{inner['match_value']!r}，会导致内层命中被外层覆盖"
                    ),
                    "severity": SEVERITY_MEDIUM,
                    "field_type": outer.get("field_type"),
                    "outer_rule_id": outer["id"],
                    "inner_rule_id": inner["id"],
                }
            )
    return results


def _detect_same_priority_diff(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    buckets: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for r in rules:
        if r.get("enabled", True):
            buckets[r.get("priority")].append(r)

    results = []
    for priority, group in buckets.items():
        if len(group) < 2:
            continue
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                strategy_a = a.get("replace_strategy")
                strategy_b = b.get("replace_strategy")
                config_a = a.get("replace_config") or {}
                config_b = b.get("replace_config") or {}
                if strategy_a != strategy_b or config_a != config_b:
                    results.append(
                        {
                            "rule_ids": sorted(
                                rid
                                for rid in (a["id"], b["id"])
                                if rid is not None
                            ),
                            "conflict_type": "same_priority_diff",
                            "message": (
                                f"规则 {a.get('rule_name')}({a['id']}) 与 "
                                f"{b.get('rule_name')}({b['id']}) 优先级同为 "
                                f"{priority}，但替换策略或配置不同，"
                                f"执行顺序不稳定可能导致结果不可预测"
                            ),
                            "severity": SEVERITY_MEDIUM,
                            "field_type": a.get("field_type"),
                            "priority": priority,
                        }
                    )
    return results
