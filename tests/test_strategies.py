"""替换策略单元测试，重点验证幂等性与短文本保护。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import strategies
from app.errors import ValidationError


class TestFixed(unittest.TestCase):
    def test_fixed_replace(self):
        self.assertEqual(strategies.apply_strategy("fixed", "13800001111", {"value": "[PHONE]"}), "[PHONE]")

    def test_fixed_idempotent(self):
        once = strategies.apply_strategy("fixed", "secret", {"value": "***"})
        twice = strategies.apply_strategy("fixed", once, {"value": "***"})
        self.assertEqual(once, twice)


class TestKeepEdges(unittest.TestCase):
    def test_basic(self):
        out = strategies.apply_strategy("keep_edges", "13800001111", {"left": 3, "right": 4, "mask_char": "*"})
        self.assertEqual(out, "138****1111")

    def test_edges_cover_all(self):
        # left+right >= 长度时保持原样，不遮蔽。
        out = strategies.apply_strategy("keep_edges", "abc", {"left": 2, "right": 2})
        self.assertEqual(out, "abc")

    def test_idempotent(self):
        cfg = {"left": 3, "right": 4, "mask_char": "*"}
        once = strategies.apply_strategy("keep_edges", "13800001111", cfg)
        twice = strategies.apply_strategy("keep_edges", once, cfg)
        self.assertEqual(once, twice)

    def test_bad_mask_char(self):
        with self.assertRaises(ValidationError):
            strategies.apply_strategy("keep_edges", "abcdef", {"mask_char": "**"})


class TestMiddleMask(unittest.TestCase):
    def test_basic(self):
        out = strategies.apply_strategy("middle_mask", "abcdef", {"keep_left": 1, "keep_right": 1})
        self.assertEqual(out, "a****f")

    def test_single_char_not_masked(self):
        # 短文本保护：单字符不能被全部遮蔽。
        out = strategies.apply_strategy("middle_mask", "a", {"keep_left": 1, "keep_right": 1})
        self.assertEqual(out, "a")

    def test_two_char_keeps_one(self):
        out = strategies.apply_strategy("middle_mask", "ab", {"keep_left": 5, "keep_right": 5})
        # 不能全部遮蔽，至少保留字符。
        self.assertNotEqual(out, "**")
        self.assertTrue(any(c != "*" for c in out))

    def test_never_all_masked(self):
        for text in ["a", "ab", "abc", "abcd", "汉字"]:
            out = strategies.apply_strategy("middle_mask", text, {"keep_left": 10, "keep_right": 10})
            self.assertTrue(any(c != "*" for c in out), f"{text} -> {out} 全部被遮蔽")

    def test_idempotent(self):
        cfg = {"keep_left": 1, "keep_right": 1}
        once = strategies.apply_strategy("middle_mask", "abcdef", cfg)
        twice = strategies.apply_strategy("middle_mask", once, cfg)
        self.assertEqual(once, twice)


class TestUnknownStrategy(unittest.TestCase):
    def test_unknown(self):
        with self.assertRaises(ValidationError):
            strategies.apply_strategy("nope", "abc", {})


if __name__ == "__main__":
    unittest.main()
