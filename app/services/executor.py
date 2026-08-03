from __future__ import annotations
"""脱敏规则执行器。"""
import json

from app.services.matcher import find_matches
from app.services.replacer import apply_replace


class RuleExecutor:

    @staticmethod
    def execute_single(text: str, rule: dict) -> dict:
        match_type = rule["match_type"]
        match_value = rule["match_value"]
        replace_strategy = rule["replace_strategy"]
        replace_config = rule.get("replace_config", {})
        if isinstance(replace_config, str):
            replace_config = json.loads(replace_config) if replace_config else {}

        matches = find_matches(match_type, match_value, text)
        hit_count = len(matches)

        output = text
        for start, end, matched_text in reversed(matches):
            replaced = apply_replace(replace_strategy, matched_text, replace_config)
            output = output[:start] + replaced + output[end:]

        hit_details = []
        if matches:
            first_matched = matches[0][2]
            after_fragment = apply_replace(replace_strategy, first_matched, replace_config)
            hit_details.append({
                "rule_id": rule["id"],
                "matched_count": hit_count,
                "before_fragment": first_matched,
                "after_fragment": after_fragment,
            })

        return {
            "output_text": output,
            "hit_count": hit_count,
            "hit_details": hit_details,
        }

    @staticmethod
    def execute_group(text: str, rules: list[dict]) -> dict:
        enabled_rules = [r for r in rules if r.get("enabled", True)]
        ordered_rules = sorted(enabled_rules, key=lambda r: r.get("priority", 100))

        current_text = text
        total_hit_count = 0
        hit_details = []

        for rule in ordered_rules:
            result = RuleExecutor.execute_single(current_text, rule)
            current_text = result["output_text"]
            total_hit_count += result["hit_count"]
            hit_details.extend(result["hit_details"])

        return {
            "output_text": current_text,
            "hit_count": total_hit_count,
            "hit_details": hit_details,
        }
