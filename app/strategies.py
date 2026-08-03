"""替换策略实现。

支持三种替换策略：

* ``fixed``      —— 将命中片段整体替换为固定文本。
* ``keep_edges`` —— 保留左右两侧若干字符，中间以掩码字符填充。
* ``middle_mask``—— 遮蔽中间部分，保留首尾；遇到短文本时不会遮蔽全部字符。

所有策略对单个命中片段的变换都是 **幂等** 的：对已脱敏片段再次应用同一
策略会得到完全相同的结果，因此同一文本重复执行同一规则不会持续增加星号。
"""

from . import config
from .errors import ValidationError


def _mask_char(replace_config):
    ch = replace_config.get("mask_char", config.DEFAULT_MASK_CHAR)
    if not isinstance(ch, str) or len(ch) != 1:
        raise ValidationError(
            "mask_char 必须是单个字符", details={"mask_char": ch}
        )
    return ch


def _mask_fixed(fragment, replace_config):
    """整体替换为固定文本。"""
    value = replace_config.get("value", "***")
    if not isinstance(value, str):
        raise ValidationError("fixed 策略的 value 必须是字符串", details={"value": value})
    return value


def _mask_keep_edges(fragment, replace_config):
    """保留左右边缘字符，中间用掩码字符替换。"""
    left = replace_config.get("left", 1)
    right = replace_config.get("right", 1)
    if not isinstance(left, int) or not isinstance(right, int) or left < 0 or right < 0:
        raise ValidationError(
            "keep_edges 的 left/right 必须是非负整数",
            details={"left": left, "right": right},
        )
    mask_char = _mask_char(replace_config)
    n = len(fragment)
    # 边缘之和覆盖或超过整个片段时，没有可遮蔽的中间部分，保持原样。
    if left + right >= n:
        return fragment
    middle_len = n - left - right
    prefix = fragment[:left]
    suffix = fragment[n - right:] if right > 0 else ""
    return prefix + mask_char * middle_len + suffix


def _mask_middle(fragment, replace_config):
    """遮蔽中间部分，保留首尾，短文本时保护至少一个字符不被遮蔽。"""
    mask_char = _mask_char(replace_config)
    keep_left = replace_config.get("keep_left", 1)
    keep_right = replace_config.get("keep_right", 1)
    if (
        not isinstance(keep_left, int)
        or not isinstance(keep_right, int)
        or keep_left < 0
        or keep_right < 0
    ):
        raise ValidationError(
            "middle_mask 的 keep_left/keep_right 必须是非负整数",
            details={"keep_left": keep_left, "keep_right": keep_right},
        )
    n = len(fragment)
    if n == 0:
        return fragment
    # 短文本保护：绝不能把全部字符都替换掉，至少保留一个字符。
    if n == 1:
        return fragment
    keep = keep_left + keep_right
    if keep >= n:
        # 保留位需求过大，退化为只遮蔽中间的单个字符，确保仍保留首尾。
        keep_left = 1
        keep_right = 1
        if keep_left + keep_right >= n:
            keep_right = 0  # n==... 保底保留左侧一个字符
    middle_len = n - keep_left - keep_right
    if middle_len <= 0:
        # 计算后无可遮蔽字符，强制遮蔽中间一位，保证不全遮蔽。
        keep_left = 1
        keep_right = max(0, n - 2)
        middle_len = n - keep_left - keep_right
    prefix = fragment[:keep_left]
    suffix = fragment[n - keep_right:] if keep_right > 0 else ""
    return prefix + mask_char * middle_len + suffix


_STRATEGIES = {
    "fixed": _mask_fixed,
    "keep_edges": _mask_keep_edges,
    "middle_mask": _mask_middle,
}


def apply_strategy(strategy, fragment, replace_config):
    """对单个命中片段应用指定替换策略。"""
    fn = _STRATEGIES.get(strategy)
    if fn is None:
        raise ValidationError(
            "不支持的替换策略",
            details={"replace_strategy": strategy, "allowed": list(_STRATEGIES)},
        )
    return fn(fragment, replace_config or {})
