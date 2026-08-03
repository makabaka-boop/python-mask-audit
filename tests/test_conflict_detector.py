"""冲突检测单元测试。"""
import unittest

from app.conflict_detector import detect_conflicts


def _rule(
    rule_id,
    *,
    field_type="phone",
    match_type="exact",
    match_value="13800000000",
    strategy="fixed",
    config=None,
    priority=100,
    enabled=True,
    rule_name=None,
):
    return {
        "id": rule_id,
        "rule_name": rule_name or f"r{rule_id}",
        "field_type": field_type,
        "match_type": match_type,
        "match_value": match_value,
        "replace_strategy": strategy,
        "replace_config": config if config is not None else {"replacement": "X"},
        "priority": priority,
        "enabled": enabled,
    }


class DuplicateExactTest(unittest.TestCase):
    def test_duplicate_exact_detected(self):
        rules = [
            _rule(1, match_value="123"),
            _rule(2, match_value="123"),
        ]
        conflicts = detect_conflicts(rules)
        dup = [c for c in conflicts if c["conflict_type"] == "duplicate_exact"]
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0]["rule_ids"], [1, 2])
        self.assertEqual(dup[0]["severity"], "high")

    def test_different_field_type_no_duplicate(self):
        rules = [
            _rule(1, field_type="phone", match_value="123"),
            _rule(2, field_type="email", match_value="123"),
        ]
        conflicts = detect_conflicts(rules)
        dup = [c for c in conflicts if c["conflict_type"] == "duplicate_exact"]
        self.assertEqual(dup, [])


class ContainsOverlapTest(unittest.TestCase):
    def test_contains_overlap(self):
        rules = [
            _rule(1, match_type="contains", match_value="secret"),
            _rule(2, match_type="contains", match_value="top secret"),
        ]
        conflicts = detect_conflicts(rules)
        overlap = [
            c for c in conflicts if c["conflict_type"] == "contains_overlap"
        ]
        self.assertEqual(len(overlap), 1)
        self.assertEqual(overlap[0]["outer_rule_id"], 2)
        self.assertEqual(overlap[0]["inner_rule_id"], 1)
        self.assertEqual(overlap[0]["severity"], "medium")

    def test_no_overlap(self):
        rules = [
            _rule(1, match_type="contains", match_value="abc"),
            _rule(2, match_type="contains", match_value="xyz"),
        ]
        conflicts = detect_conflicts(rules)
        overlap = [
            c for c in conflicts if c["conflict_type"] == "contains_overlap"
        ]
        self.assertEqual(overlap, [])


class SamePriorityDiffTest(unittest.TestCase):
    def test_same_priority_different_strategy(self):
        rules = [
            _rule(
                1,
                strategy="fixed",
                config={"replacement": "X"},
                priority=50,
            ),
            _rule(
                2,
                strategy="fixed",
                config={"replacement": "Y"},
                priority=50,
            ),
        ]
        conflicts = detect_conflicts(rules)
        same = [
            c for c in conflicts if c["conflict_type"] == "same_priority_diff"
        ]
        self.assertEqual(len(same), 1)
        self.assertEqual(same[0]["rule_ids"], [1, 2])
        self.assertEqual(same[0]["severity"], "medium")

    def test_same_priority_same_config_no_conflict(self):
        rules = [
            _rule(1, strategy="fixed", config={"replacement": "X"}, priority=10),
            _rule(2, strategy="fixed", config={"replacement": "X"}, priority=10),
        ]
        conflicts = detect_conflicts(rules)
        same = [
            c for c in conflicts if c["conflict_type"] == "same_priority_diff"
        ]
        self.assertEqual(same, [])

    def test_different_priority_no_conflict(self):
        rules = [
            _rule(1, strategy="fixed", config={"replacement": "X"}, priority=10),
            _rule(2, strategy="fixed", config={"replacement": "Y"}, priority=20),
        ]
        conflicts = detect_conflicts(rules)
        same = [
            c for c in conflicts if c["conflict_type"] == "same_priority_diff"
        ]
        self.assertEqual(same, [])


if __name__ == "__main__":
    unittest.main()
