from __future__ import annotations
"""文本匹配策略。"""
import re


def find_matches(match_type: str, match_value: str, text: str) -> list[tuple[int, int, str]]:
    if match_type in ("exact", "contains"):
        results: list[tuple[int, int, str]] = []
        if not match_value:
            return results
        start = 0
        while True:
            idx = text.find(match_value, start)
            if idx == -1:
                break
            results.append((idx, idx + len(match_value), match_value))
            start = idx + len(match_value)
        return results

    if match_type == "regex":
        try:
            pattern = re.compile(match_value)
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern: {exc}") from exc
        return [(m.start(), m.end(), m.group()) for m in pattern.finditer(text)]

    raise ValueError(f"Unknown match type: {match_type}")
