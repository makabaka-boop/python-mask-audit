"""规则执行器单元测试。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import executor
from app.errors import ValidationError


def rule(match_type, match_value, strategy="fixed", cfg=None):
    return {
        "id": 1,
        "match_type": match_type,
        "match_value": match_value,
        "replace_strategy": strategy,
        "replace_config": cfg or {"value": "***"},
    }


class TestExecuteRule(unittest.TestCase):
    def test_exact_hit(self):
        out, count, _, _ = executor.execute_rule(rule("exact", "secret"), "secret")
        self.assertEqual(out, "***")
        self.assertEqual(count, 1)

    def test_exact_no_hit(self):
        out, count, _, _ = executor.execute_rule(rule("exact", "secret"), "not secret here")
        self.assertEqual(count, 0)
        self.assertEqual(out, "not secret here")

    def test_contains(self):
        out, count, _, _ = executor.execute_rule(rule("contains", "foo"), "foo bar foo")
        self.assertEqual(count, 2)
        self.assertEqual(out, "*** bar ***")

    def test_regex(self):
        r = rule("regex", r"\d{4}", strategy="keep_edges", cfg={"left": 1, "right": 1})
        out, count, before, after = executor.execute_rule(r, "id 1234 and 5678")
        self.assertEqual(count, 2)
        self.assertEqual(before, "1234")
        self.assertEqual(after, "1**4")

    def test_regex_invalid(self):
        with self.assertRaises(ValidationError):
            executor.execute_rule(rule("regex", "([a-z"), "abc")

    def test_empty_match_value(self):
        with self.assertRaises(ValidationError):
            executor.execute_rule(rule("contains", ""), "abc")

    def test_idempotent_regex(self):
        r = rule("regex", r"\d{4}", strategy="keep_edges", cfg={"left": 1, "right": 1})
        out1, _, _, _ = executor.execute_rule(r, "id 1234")
        out2, _, _, _ = executor.execute_rule(r, out1)
        self.assertEqual(out1, out2)

    def test_idempotent_contains_fixed(self):
        r = rule("contains", "secret", strategy="fixed", cfg={"value": "***"})
        out1, _, _, _ = executor.execute_rule(r, "secret secret")
        out2, _, _, _ = executor.execute_rule(r, out1)
        self.assertEqual(out1, out2)


class TestExecuteRules(unittest.TestCase):
    def test_chain(self):
        rules = [
            rule("contains", "foo", cfg={"value": "F"}),
            rule("contains", "bar", cfg={"value": "B"}),
        ]
        out, total, details = executor.execute_rules(rules, "foo bar baz")
        self.assertEqual(out, "F B baz")
        self.assertEqual(total, 2)
        self.assertEqual(len(details), 2)

    def test_no_star_growth(self):
        # 同一文本重复执行同一组规则，星号不应持续增长。
        rules = [rule("regex", r"\d{4}", strategy="keep_edges", cfg={"left": 1, "right": 1})]
        out1, _, _ = executor.execute_rules(rules, "code 1234")
        out2, _, _ = executor.execute_rules(rules, out1)
        out3, _, _ = executor.execute_rules(rules, out2)
        self.assertEqual(out1, out2)
        self.assertEqual(out2, out3)


if __name__ == "__main__":
    unittest.main()
