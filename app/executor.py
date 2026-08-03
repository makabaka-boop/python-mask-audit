"""规则执行器。

负责将一条脱敏规则应用到文本上，返回脱敏结果与命中明细。

匹配方式：

* ``exact``    —— 整段文本与 ``match_value`` 完全相等时命中一次。
* ``contains`` —— 将文本中所有等于 ``match_value`` 的子串命中并替换。
* ``regex``    —— 按正则匹配文本中的所有片段并替换。

幂等性：每种替换策略对单个片段都是幂等的（见 ``strategies``），
因此对同一文本重复执行同一规则不会产生持续增加的掩码字符。
"""

import re

from . import strategies
from .errors import ValidationError


def compile_pattern(match_type, match_value):
    """根据匹配方式返回可复用的匹配对象；regex 会在此处编译校验。"""
    if match_value is None or match_value == "":
        raise ValidationError("match_value 不能为空", details={"match_value": match_value})
    if match_type == "regex":
        try:
            return re.compile(match_value)
        except re.error as exc:
            raise ValidationError(
                "regex 编译失败", details={"match_value": match_value, "reason": str(exc)}
            )
    return None


def execute_rule(rule, text):
    """对 ``text`` 执行单条规则。

    ``rule`` 为包含 match_type / match_value / replace_strategy /
    replace_config 字段的字典（或 sqlite3.Row 兼容映射）。

    返回 ``(output_text, matched_count, before_fragment, after_fragment)``。
    ``before_fragment`` / ``after_fragment`` 为首个命中片段的前后对照，便于审计。
    """
    match_type = rule["match_type"]
    match_value = rule["match_value"]
    strategy = rule["replace_strategy"]
    replace_config = rule["replace_config"] or {}

    if match_value is None or match_value == "":
        raise ValidationError("match_value 不能为空", details={"match_value": match_value})

    before_fragment = ""
    after_fragment = ""
    matched_count = 0

    if match_type == "exact":
        # 整段文本完全相等才命中。
        if text == match_value:
            replaced = strategies.apply_strategy(strategy, text, replace_config)
            before_fragment = text
            after_fragment = replaced
            return replaced, 1, before_fragment, after_fragment
        return text, 0, "", ""

    if match_type == "contains":
        if match_value not in text:
            return text, 0, "", ""
        # 逐个替换字面子串，统计命中次数。
        count = text.count(match_value)
        replaced_fragment = strategies.apply_strategy(strategy, match_value, replace_config)
        output = text.replace(match_value, replaced_fragment)
        return output, count, match_value, replaced_fragment

    if match_type == "regex":
        pattern = compile_pattern(match_type, match_value)
        state = {"count": 0, "before": "", "after": ""}

        def _repl(m):
            fragment = m.group(0)
            replaced = strategies.apply_strategy(strategy, fragment, replace_config)
            if state["count"] == 0:
                state["before"] = fragment
                state["after"] = replaced
            state["count"] += 1
            return replaced

        output = pattern.sub(_repl, text)
        return output, state["count"], state["before"], state["after"]

    raise ValidationError(
        "不支持的匹配方式",
        details={"match_type": match_type, "allowed": ["exact", "contains", "regex"]},
    )


def execute_rules(rules, text):
    """按顺序执行多条规则（调用方需已按 priority 排序）。

    返回 ``(output_text, total_hits, hit_details)``，其中 ``hit_details``
    为每条命中规则的明细列表。
    """
    current = text
    total_hits = 0
    details = []
    for rule in rules:
        output, matched_count, before, after = execute_rule(rule, current)
        if matched_count > 0:
            details.append(
                {
                    "rule_id": rule["id"],
                    "matched_count": matched_count,
                    "before_fragment": before,
                    "after_fragment": after,
                }
            )
            total_hits += matched_count
        current = output
    return current, total_hits, details
