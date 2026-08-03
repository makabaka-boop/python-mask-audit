from __future__ import annotations
"""规则冲突检测服务。"""
import json
from itertools import combinations


class ConflictDetector:

    DUPLICATE_EXACT = "duplicate_exact"
    CONTAINS_OVERLAP = "contains_overlap"
    PRIORITY_CONFLICT = "priority_conflict"

    SEVERITY_HIGH = "high"
    SEVERITY_MEDIUM = "medium"
    SEVERITY_LOW = "low"

    @staticmethod
    def _parse_config(rule: dict) -> dict:
        cfg = rule.get("replace_config", {})
        if isinstance(cfg, str):
            cfg = json.loads(cfg) if cfg else {}
        return cfg

    @staticmethod
    def detect(rules: list[dict]) -> list[dict]:
        conflicts: list[dict] = []

        enabled_rules = [r for r in rules if r.get("enabled", True)]

        ConflictDetector._detect_duplicate_exact(enabled_rules, conflicts)
        ConflictDetector._detect_contains_overlap(enabled_rules, conflicts)
        ConflictDetector._detect_priority_conflict(enabled_rules, conflicts)

        return conflicts

    @staticmethod
    def _detect_duplicate_exact(rules: list[dict], conflicts: list[dict]) -> None:
        groups: dict[tuple, list[dict]] = {}
        for rule in rules:
            if rule.get("match_type") != "exact":
                continue
            key = (rule.get("field_type", ""), rule.get("match_value", ""))
            groups.setdefault(key, []).append(rule)

        for (field_type, match_value), group_rules in groups.items():
            if len(group_rules) >= 2:
                rule_ids = sorted(r["id"] for r in group_rules)
                conflicts.append({
                    "rule_ids": rule_ids,
                    "conflict_type": ConflictDetector.DUPLICATE_EXACT,
                    "message": (
                        f"字段类型 '{field_type}' 下存在 {len(group_rules)} 条 "
                        f"完全相同的 exact 规则 (match_value='{match_value}')，"
                        f"会导致重复脱敏"
                    ),
                    "severity": ConflictDetector.SEVERITY_HIGH,
                })

    @staticmethod
    def _detect_contains_overlap(rules: list[dict], conflicts: list[dict]) -> None:
        contains_rules = [
            r for r in rules if r.get("match_type") in ("contains", "exact")
        ]

        by_field: dict[str, list[dict]] = {}
        for rule in contains_rules:
            by_field.setdefault(rule.get("field_type", ""), []).append(rule)

        seen_pairs: set[tuple[int, int]] = set()
        for field_type, field_rules in by_field.items():
            for r1, r2 in combinations(field_rules, 2):
                v1 = r1.get("match_value", "")
                v2 = r2.get("match_value", "")
                if not v1 or not v2 or v1 == v2:
                    continue
                pair = tuple(sorted([r1["id"], r2["id"]]))
                if pair in seen_pairs:
                    continue

                if v1 in v2 or v2 in v1:
                    seen_pairs.add(pair)
                    shorter = r1 if len(v1) <= len(v2) else r2
                    longer = r2 if len(v1) <= len(v2) else r1
                    sid = shorter["id"]
                    lid = longer["id"]
                    sval = shorter.get("match_value", "")
                    lval = longer.get("match_value", "")
                    conflicts.append({
                        "rule_ids": [sid, lid],
                        "conflict_type": ConflictDetector.CONTAINS_OVERLAP,
                        "message": (
                            "字段类型 '" + field_type + "' 下规则 " + str(sid)
                            + " ('" + sval + "') 的匹配值被规则 "
                            + str(lid) + " ('" + lval + "') "
                            + "包含，可能导致先执行的规则覆盖后执行规则的匹配范围"
                        ),
                        "severity": ConflictDetector.SEVERITY_MEDIUM,
                    })

    @staticmethod
    def _detect_priority_conflict(rules: list[dict], conflicts: list[dict]) -> None:
        by_priority: dict[int, list[dict]] = {}
        for rule in rules:
            priority = rule.get("priority", 100)
            by_priority.setdefault(priority, []).append(rule)

        for priority, group_rules in by_priority.items():
            if len(group_rules) < 2:
                continue

            for r1, r2 in combinations(group_rules, 2):
                cfg1 = ConflictDetector._parse_config(r1)
                cfg2 = ConflictDetector._parse_config(r2)
                strategy_differs = (
                    r1.get("replace_strategy") != r2.get("replace_strategy")
                )
                config_differs = cfg1 != cfg2

                if strategy_differs or config_differs:
                    pair = tuple(sorted([r1["id"], r2["id"]]))
                    diff_desc = []
                    if strategy_differs:
                        diff_desc.append(
                            f"替换策略 {r1.get('replace_strategy')} vs "
                            f"{r2.get('replace_strategy')}"
                        )
                    if config_differs:
                        diff_desc.append("替换配置不同")

                    conflicts.append({
                        "rule_ids": list(pair),
                        "conflict_type": ConflictDetector.PRIORITY_CONFLICT,
                        "message": (
                            f"规则 {r1['id']} 与 {r2['id']} 优先级相同 "
                            f"(priority={priority})，但 {' 且 '.join(diff_desc)}，"
                            f"执行顺序不确定可能导致结果不稳定"
                        ),
                        "severity": ConflictDetector.SEVERITY_MEDIUM,
                    })
