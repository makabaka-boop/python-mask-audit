"""替换策略：fixed / keep_edges / middle_mask。

所有策略必须幂等：对已经脱敏过的片段再次执行，不能持续增加掩码字符。
"""

DEFAULT_MASK_CHAR = "*"


def _mask_char(config: dict) -> str:
    ch = (config or {}).get("mask_char") or DEFAULT_MASK_CHAR
    if not isinstance(ch, str) or len(ch) != 1:
        raise ValueError("mask_char 必须是单个字符")
    return ch


def _all_mask(text: str, mask_char: str) -> bool:
    return len(text) > 0 and all(c == mask_char for c in text)


def fixed(fragment: str, config: dict) -> str:
    """整体替换为固定内容。"""
    replacement = (config or {}).get("replacement", "***")
    if not isinstance(replacement, str) or replacement == "":
        raise ValueError("fixed 策略的 replacement 不能为空")
    if fragment == replacement:  # 幂等：已是替换结果
        return fragment
    return replacement


def keep_edges(fragment: str, config: dict) -> str:
    """保留左右边缘字符，中间打码。"""
    config = config or {}
    left = int(config.get("left", 1))
    right = int(config.get("right", 1))
    if left < 0 or right < 0:
        raise ValueError("keep_edges 的 left/right 不能为负数")
    ch = _mask_char(config)
    n = len(fragment)
    if n <= 1:
        return fragment
    if n <= left + right:  # 短文本兜底：至少保留首字符
        left, right = 1, 0
    middle = fragment[left:n - right] if right else fragment[left:]
    if _all_mask(middle, ch):  # 幂等：中间已全部是掩码
        return fragment
    return fragment[:left] + ch * len(middle) + (fragment[n - right:] if right else "")


def middle_mask(fragment: str, config: dict) -> str:
    """保留首尾字符，中间打码；短文本不能把全部字符替换掉。"""
    config = config or {}
    ch = _mask_char(config)
    n = len(fragment)
    if n <= 1:
        return fragment
    mask_count = config.get("mask_count")
    if mask_count is not None:
        mask_count = int(mask_count)
        if mask_count < 1:
            raise ValueError("middle_mask 的 mask_count 必须为正整数")
    if n == 2:
        return fragment[0] + ch * (mask_count or 1) if mask_count else fragment[0] + ch
    middle = fragment[1:-1]
    if _all_mask(middle, ch):  # 幂等
        return fragment
    count = mask_count if mask_count is not None else len(middle)
    return fragment[0] + ch * count + fragment[-1]


STRATEGIES = {
    "fixed": fixed,
    "keep_edges": keep_edges,
    "middle_mask": middle_mask,
}
