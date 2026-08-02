"""规则校验器。"""
from __future__ import annotations

import re
from typing import Any, Dict, Tuple

from .errors import RegexCompileError, ValidationError

MATCH_TYPES = {"exact", "contains", "regex"}
REPLACE_STRATEGIES = {"fixed", "keep_edges", "middle_mask"}


def validate_match_type(match_type: str) -> None:
    if match_type not in MATCH_TYPES:
        raise ValidationError(
            "match_type 非法",
            details={"allowed": sorted(MATCH_TYPES), "received": match_type},
        )


def validate_replace_strategy(strategy: str) -> None:
    if strategy not in REPLACE_STRATEGIES:
        raise ValidationError(
            "replace_strategy 非法",
            details={"allowed": sorted(REPLACE_STRATEGIES), "received": strategy},
        )


def compile_regex(pattern: str) -> re.Pattern:
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise RegexCompileError(
            "正则表达式无法编译", details={"pattern": pattern, "error": str(exc)}
        )


def validate_rule_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationError("请求体必须是 JSON 对象")

    rule_name = payload.get("rule_name")
    field_type = payload.get("field_type")
    match_type = payload.get("match_type")
    match_value = payload.get("match_value")
    replace_strategy = payload.get("replace_strategy")
    replace_config = payload.get("replace_config", {})

    if not rule_name or not isinstance(rule_name, str):
        raise ValidationError("rule_name 不能为空", details={"field": "rule_name"})
    if not field_type or not isinstance(field_type, str):
        raise ValidationError("field_type 不能为空", details={"field": "field_type"})
    if not match_type or not isinstance(match_type, str):
        raise ValidationError("match_type 不能为空", details={"field": "match_type"})
    validate_match_type(match_type)

    if match_value is None or not isinstance(match_value, str) or match_value == "":
        raise ValidationError("match_value 不能为空", details={"field": "match_value"})

    if not replace_strategy or not isinstance(replace_strategy, str):
        raise ValidationError(
            "replace_strategy 不能为空", details={"field": "replace_strategy"}
        )
    validate_replace_strategy(replace_strategy)

    if replace_config is None:
        replace_config = {}
    if not isinstance(replace_config, dict):
        raise ValidationError(
            "replace_config 必须是对象", details={"field": "replace_config"}
        )

    if replace_strategy == "fixed":
        if "replacement" not in replace_config or not isinstance(
            replace_config["replacement"], str
        ):
            raise ValidationError(
                "fixed 策略需要 replace_config.replacement 字符串",
                details={"field": "replace_config.replacement"},
            )
    elif replace_strategy == "keep_edges":
        left = replace_config.get("left", 0)
        right = replace_config.get("right", 0)
        mask_char = replace_config.get("mask_char", "*")
        if not isinstance(left, int) or left < 0:
            raise ValidationError(
                "keep_edges.left 必须是非负整数",
                details={"field": "replace_config.left"},
            )
        if not isinstance(right, int) or right < 0:
            raise ValidationError(
                "keep_edges.right 必须是非负整数",
                details={"field": "replace_config.right"},
            )
        if not isinstance(mask_char, str) or len(mask_char) != 1:
            raise ValidationError(
                "keep_edges.mask_char 必须是单字符",
                details={"field": "replace_config.mask_char"},
            )
    elif replace_strategy == "middle_mask":
        mask_char = replace_config.get("mask_char", "*")
        if not isinstance(mask_char, str) or len(mask_char) != 1:
            raise ValidationError(
                "middle_mask.mask_char 必须是单字符",
                details={"field": "replace_config.mask_char"},
            )

    if match_type == "regex":
        compile_regex(match_value)

    priority = payload.get("priority", 100)
    if not isinstance(priority, int) or priority < 0:
        raise ValidationError(
            "priority 必须是非负整数", details={"field": "priority"}
        )

    enabled = payload.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValidationError("enabled 必须是布尔值", details={"field": "enabled"})

    return {
        "rule_name": rule_name,
        "field_type": field_type,
        "match_type": match_type,
        "match_value": match_value,
        "replace_strategy": replace_strategy,
        "replace_config": replace_config,
        "priority": priority,
        "enabled": enabled,
    }


def normalize_whitespace(text: str) -> str:
    return text.strip() if isinstance(text, str) else text
