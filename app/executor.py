"""规则执行器：校验规则、匹配文本、按优先级顺序执行脱敏。"""

import json
import re
from typing import List, Tuple

from .errors import validation_error
from .strategies import STRATEGIES

MATCH_TYPES = ("exact", "contains", "regex")
REPLACE_STRATEGIES = ("fixed", "keep_edges", "middle_mask")

REQUIRED_FIELDS = ("rule_name", "field_type", "match_type", "match_value", "replace_strategy")


def validate_rule_payload(data: dict) -> dict:
    """校验创建规则的请求体，返回规范化后的字段。regex 入库前必须编译通过。"""
    if not isinstance(data, dict):
        raise validation_error("请求体必须是 JSON 对象")
    missing = [f for f in REQUIRED_FIELDS if data.get(f) in (None, "")]
    if missing:
        raise validation_error("缺少必填字段", {"missing_fields": missing})

    match_type = data["match_type"]
    if match_type not in MATCH_TYPES:
        raise validation_error("match_type 只允许 exact / contains / regex",
                               {"match_type": match_type})

    replace_strategy = data["replace_strategy"]
    if replace_strategy not in REPLACE_STRATEGIES:
        raise validation_error("replace_strategy 只允许 fixed / keep_edges / middle_mask",
                               {"replace_strategy": replace_strategy})

    match_value = data["match_value"]
    if not isinstance(match_value, str) or match_value.strip() == "":
        raise validation_error("match_value 不能为空")
    if match_type == "regex":
        try:
            re.compile(match_value)
        except re.error as exc:
            raise validation_error("match_value 不是合法的正则表达式",
                                   {"regex_error": str(exc)})

    replace_config = data.get("replace_config") or {}
    if not isinstance(replace_config, dict):
        raise validation_error("replace_config 必须是对象")

    priority = data.get("priority", 0)
    if not isinstance(priority, int):
        raise validation_error("priority 必须是整数")

    # 用策略函数试跑一次，提前暴露 replace_config 非法值
    try:
        STRATEGIES[replace_strategy]("测试片段abc", replace_config)
    except (ValueError, TypeError) as exc:
        raise validation_error("replace_config 非法", {"reason": str(exc)})

    return {
        "rule_name": str(data["rule_name"]),
        "field_type": str(data["field_type"]),
        "match_type": match_type,
        "match_value": match_value,
        "replace_strategy": replace_strategy,
        "replace_config": json.dumps(replace_config, ensure_ascii=False),
        "priority": priority,
        "enabled": 1 if data.get("enabled", True) else 0,
    }


def _find_spans(text: str, match_type: str, match_value: str) -> List[Tuple[int, int]]:
    """返回非重叠匹配区间 [start, end)。"""
    spans = []
    if match_type == "exact":
        start = 0
        while True:
            idx = text.find(match_value, start)
            if idx < 0:
                break
            spans.append((idx, idx + len(match_value)))
            start = idx + len(match_value)
    elif match_type == "contains":
        start, lower_text, lower_value = 0, text.lower(), match_value.lower()
        while True:
            idx = lower_text.find(lower_value, start)
            if idx < 0:
                break
            spans.append((idx, idx + len(match_value)))
            start = idx + len(match_value)
    else:  # regex
        for m in re.finditer(match_value, text):
            if m.end() > m.start():
                spans.append((m.start(), m.end()))
    return spans


def apply_rule(text: str, rule: dict):
    """对文本执行单条规则，返回 (输出文本, 命中数, 原始片段列表, 脱敏片段列表)。"""
    raw_config = rule["replace_config"]
    config = json.loads(raw_config) if isinstance(raw_config, str) else (raw_config or {})
    strategy = STRATEGIES[rule["replace_strategy"]]
    spans = _find_spans(text, rule["match_type"], rule["match_value"])
    if not spans:
        return text, 0, [], []

    parts, before_list, after_list = [], [], []
    cursor = 0
    for start, end in spans:
        fragment = text[start:end]
        replaced = strategy(fragment, config)
        parts.append(text[cursor:start])
        parts.append(replaced)
        if replaced != fragment:
            before_list.append(fragment)
            after_list.append(replaced)
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts), len(before_list), before_list, after_list


def sort_rules(rules: List[dict]) -> List[dict]:
    """优先级高的先执行，同优先级按规则 ID 升序，保证可重复。"""
    return sorted(rules, key=lambda r: (-r["priority"], r["id"]))


def execute_rules(text: str, rules: List[dict]):
    """按优先级顺序执行多条规则，返回 (输出文本, 每规则命中明细)。"""
    hits = []
    current = text
    for rule in sort_rules(rules):
        current, count, before_list, after_list = apply_rule(current, rule)
        hits.append({
            "rule_id": rule["id"],
            "matched_count": count,
            "before_fragment": " | ".join(before_list[:20]),
            "after_fragment": " | ".join(after_list[:20]),
        })
    return current, hits
