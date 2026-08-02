"""替换策略实现。

每个策略接收原始匹配片段（matched_text）与配置，返回脱敏后的字符串。
所有策略均基于原始匹配片段计算，天然具备幂等性——重复执行不会改变结果。
"""
from __future__ import annotations

from typing import Callable, Dict


def fixed_replace(matched_text: str, config: Dict) -> str:
    return str(config.get("replacement", ""))


def keep_edges_replace(matched_text: str, config: Dict) -> str:
    left = int(config.get("left", 0))
    right = int(config.get("right", 0))
    mask_char = config.get("mask_char", "*")
    length = len(matched_text)
    if length == 0:
        return matched_text
    if left + right >= length:
        return matched_text
    middle_len = length - left - right
    return matched_text[:left] + (mask_char * middle_len) + matched_text[length - right:]


def middle_mask_replace(matched_text: str, config: Dict) -> str:
    mask_char = config.get("mask_char", "*")
    length = len(matched_text)
    if length <= 2:
        return matched_text
    middle_len = length - 2
    return matched_text[0] + (mask_char * middle_len) + matched_text[-1]


STRATEGIES: Dict[str, Callable[[str, Dict], str]] = {
    "fixed": fixed_replace,
    "keep_edges": keep_edges_replace,
    "middle_mask": middle_mask_replace,
}


def apply_strategy(strategy_name: str, matched_text: str, config: Dict) -> str:
    func = STRATEGIES.get(strategy_name)
    if func is None:
        raise ValueError(f"未知替换策略: {strategy_name}")
    return func(matched_text, config or {})
