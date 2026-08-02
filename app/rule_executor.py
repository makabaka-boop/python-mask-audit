"""规则执行器。

执行流程：
1. 基于原始输入文本定位匹配区间。
2. 按规则配置对每个匹配片段执行替换。
3. 从后往前替换，保证前面区间偏移不被破坏。
4. 所有替换都基于“原始匹配片段”，因此同一文本重复执行同一规则结果一致（幂等）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .strategies import apply_strategy
from .validators import compile_regex


@dataclass
class HitSegment:
    start: int
    end: int
    matched_text: str
    replaced_text: str


@dataclass
class RuleHitDetail:
    rule_id: Optional[int]
    matched_count: int
    before_fragment: str
    after_fragment: str
    segments: List[HitSegment] = field(default_factory=list)


@dataclass
class ExecutionResult:
    output_text: str
    hit_count: int
    details: List[RuleHitDetail]


def _find_matches(
    text: str, match_type: str, match_value: str
) -> List[Tuple[int, int, str]]:
    if match_type == "exact":
        matches = []
        start = 0
        while True:
            idx = text.find(match_value, start)
            if idx == -1:
                break
            end = idx + len(match_value)
            matches.append((idx, end, match_value))
            if len(match_value) == 0:
                break
            start = end
        return matches
    if match_type == "contains":
        matches = []
        start = 0
        while True:
            idx = text.find(match_value, start)
            if idx == -1:
                break
            end = idx + len(match_value)
            matches.append((idx, end, match_value))
            start = end
        return matches
    if match_type == "regex":
        pattern = compile_regex(match_value)
        results = []
        for m in pattern.finditer(text):
            if m.group(0) == "" and m.start() == m.end():
                continue
            results.append((m.start(), m.end(), m.group(0)))
        return results
    raise ValueError(f"未知匹配类型: {match_type}")


def execute_rule_on_text(
    text: str,
    rule: Dict[str, Any],
    rule_id: Optional[int] = None,
) -> RuleHitDetail:
    """对一段文本执行单条规则，返回命中明细（含替换后的片段）。"""
    matches = _find_matches(
        text, rule["match_type"], rule["match_value"]
    )

    strategy = rule["replace_strategy"]
    config = rule.get("replace_config") or {}

    segments: List[HitSegment] = []
    for start, end, matched_text in matches:
        replaced_text = apply_strategy(strategy, matched_text, config)
        segments.append(
            HitSegment(
                start=start,
                end=end,
                matched_text=matched_text,
                replaced_text=replaced_text,
            )
        )

    after_fragment = _build_output(text, segments)
    return RuleHitDetail(
        rule_id=rule_id,
        matched_count=len(segments),
        before_fragment=text,
        after_fragment=after_fragment,
        segments=segments,
    )


def execute_rules_on_text(
    text: str,
    rules: List[Dict[str, Any]],
) -> ExecutionResult:
    """按 priority 升序依次执行多条规则。

    为保证幂等与可追踪，每条规则都基于当前文本定位匹配，
    但其替换内容由原始匹配片段决定，不会因已存在的掩码字符而再次扩展掩码。
    """
    sorted_rules = sorted(
        rules,
        key=lambda r: (r.get("priority", 100), r.get("id") or 0),
    )

    current_text = text
    all_details: List[RuleHitDetail] = []
    total_hits = 0

    for rule in sorted_rules:
        if not rule.get("enabled", True):
            continue
        detail = execute_rule_on_text(
            current_text,
            rule,
            rule_id=rule.get("id"),
        )
        current_text = detail.after_fragment
        if detail.matched_count > 0:
            total_hits += detail.matched_count
            all_details.append(detail)

    return ExecutionResult(
        output_text=current_text,
        hit_count=total_hits,
        details=all_details,
    )


def _build_output(text: str, segments: List[HitSegment]) -> str:
    if not segments:
        return text
    # 从后向前替换，避免偏移变化
    sorted_segments = sorted(segments, key=lambda s: s.start, reverse=True)
    chars = list(text)
    for seg in sorted_segments:
        chars[seg.start:seg.end] = list(seg.replaced_text)
    return "".join(chars)


def fragment_snippet(text: str, start: int, end: int, radius: int = 20) -> str:
    s = max(0, start - radius)
    e = min(len(text), end + radius)
    prefix = "..." if s > 0 else ""
    suffix = "..." if e < len(text) else ""
    return prefix + text[s:e] + suffix
