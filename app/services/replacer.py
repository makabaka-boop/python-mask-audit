from __future__ import annotations
"""脱敏替换策略。"""


def fixed_replace(matched_text: str, config: dict) -> str:
    return config.get("replacement", "***")


def keep_edges_replace(matched_text: str, config: dict) -> str:
    left = int(config.get("left", 1))
    right = int(config.get("right", 1))
    mask_char = config.get("mask_char", "*")
    n = len(matched_text)

    if n == 0:
        return matched_text

    if n <= left:
        return matched_text[0] + mask_char * (n - 1)

    if n <= left + right:
        return matched_text[:left] + mask_char * (n - left)

    middle = matched_text[left:n - right]
    if middle and all(ch == mask_char for ch in middle):
        return matched_text

    return matched_text[:left] + mask_char * len(middle) + matched_text[n - right:]


def middle_mask_replace(matched_text: str, config: dict) -> str:
    mask_char = config.get("mask_char", "*")
    n = len(matched_text)

    if n <= 2:
        return matched_text

    inner = matched_text[1:n - 1]
    if inner and all(ch == mask_char for ch in inner):
        return matched_text

    return matched_text[0] + mask_char * len(inner) + matched_text[n - 1]


_STRATEGIES = {
    "fixed": fixed_replace,
    "keep_edges": keep_edges_replace,
    "middle_mask": middle_mask_replace,
}


def apply_replace(strategy: str, matched_text: str, config: dict) -> str:
    if strategy not in _STRATEGIES:
        raise ValueError(f"Unknown replace strategy: {strategy}")
    return _STRATEGIES[strategy](matched_text, config)
