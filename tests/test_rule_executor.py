"""规则执行器测试（含幂等性）。"""
import unittest

from app.rule_executor import execute_rule_on_text, execute_rules_on_text


class RuleExecutorTest(unittest.TestCase):
    def _rule(
        self,
        match_type="exact",
        match_value="secret",
        strategy="fixed",
        config=None,
        priority=100,
        enabled=True,
        rule_id=1,
    ):
        return {
            "id": rule_id,
            "match_type": match_type,
            "match_value": match_value,
            "replace_strategy": strategy,
            "replace_config": config or {"replacement": "[X]"},
            "priority": priority,
            "enabled": enabled,
        }

    def test_exact_match(self):
        detail = execute_rule_on_text(
            "a secret b", self._rule(match_value="secret")
        )
        self.assertEqual(detail.matched_count, 1)
        self.assertEqual(detail.after_fragment, "a [X] b")

    def test_contains_match(self):
        detail = execute_rule_on_text(
            "xxsecretxx", self._rule(match_type="contains", match_value="secret")
        )
        self.assertEqual(detail.after_fragment, "xx[X]xx")

    def test_regex_multiple_matches(self):
        rule = self._rule(
            match_type="regex",
            match_value=r"\d{4}",
            strategy="fixed",
            config={"replacement": "****"},
        )
        detail = execute_rule_on_text("1111 2222 3333", rule)
        self.assertEqual(detail.matched_count, 3)
        self.assertEqual(detail.after_fragment, "**** **** ****")

    def test_idempotent_already_masked(self):
        """对已经脱敏过的文本再执行同一规则，不能命中原始模式，结果稳定。"""
        rule = self._rule(
            match_type="regex",
            match_value=r"1[3-9]\d{9}",
            strategy="keep_edges",
            config={"left": 3, "right": 2, "mask_char": "*"},
        )
        first = execute_rule_on_text("call 13812345678 now", rule)
        self.assertEqual(first.after_fragment, "call 138******78 now")
        second = execute_rule_on_text(first.after_fragment, rule)
        self.assertEqual(second.matched_count, 0)
        self.assertEqual(second.after_fragment, first.after_fragment)

    def test_rules_priority_order(self):
        """priority 越小越先执行。"""
        first = self._rule(
            match_value="a",
            strategy="fixed",
            config={"replacement": "X"},
            priority=10,
            rule_id=1,
        )
        second = self._rule(
            match_value="X",
            strategy="fixed",
            config={"replacement": "Y"},
            priority=20,
            rule_id=2,
        )
        result = execute_rules_on_text("a", [second, first])
        self.assertEqual(result.output_text, "Y")
        self.assertEqual(result.hit_count, 2)

    def test_disabled_rule_skipped(self):
        disabled = self._rule(enabled=False, rule_id=1)
        result = execute_rules_on_text("a secret b", [disabled])
        self.assertEqual(result.hit_count, 0)
        self.assertEqual(result.output_text, "a secret b")


if __name__ == "__main__":
    unittest.main()
