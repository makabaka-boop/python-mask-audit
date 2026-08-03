"""替换策略单元测试。"""
import unittest

from app.strategies import (
    fixed_replace,
    keep_edges_replace,
    middle_mask_replace,
    apply_strategy,
)


class FixedStrategyTest(unittest.TestCase):
    def test_fixed(self):
        self.assertEqual(
            fixed_replace("secret", {"replacement": "[X]"}), "[X]"
        )

    def test_fixed_empty(self):
        self.assertEqual(fixed_replace("anything", {"replacement": ""}), "")


class KeepEdgesTest(unittest.TestCase):
    def test_keep_edges(self):
        self.assertEqual(
            keep_edges_replace("13812345678", {"left": 3, "right": 2, "mask_char": "*"}),
            "138******78",
        )

    def test_keep_edges_left_plus_right_ge_length(self):
        self.assertEqual(
            keep_edges_replace("ab", {"left": 1, "right": 1, "mask_char": "*"}),
            "ab",
        )

    def test_keep_edges_zero(self):
        self.assertEqual(
            keep_edges_replace("abcde", {"left": 0, "right": 0, "mask_char": "#"}),
            "#####",
        )


class MiddleMaskTest(unittest.TestCase):
    def test_long(self):
        self.assertEqual(middle_mask_replace("abcdef", {"mask_char": "*"}), "a****f")

    def test_three(self):
        self.assertEqual(middle_mask_replace("abc", {"mask_char": "*"}), "a*c")

    def test_two_unchanged(self):
        self.assertEqual(middle_mask_replace("ab", {"mask_char": "*"}), "ab")

    def test_one_unchanged(self):
        self.assertEqual(middle_mask_replace("a", {"mask_char": "*"}), "a")

    def test_empty(self):
        self.assertEqual(middle_mask_replace("", {"mask_char": "*"}), "")


class ApplyStrategyTest(unittest.TestCase):
    def test_dispatch(self):
        self.assertEqual(
            apply_strategy("fixed", "x", {"replacement": "Y"}), "Y"
        )

    def test_unknown(self):
        with self.assertRaises(ValueError):
            apply_strategy("unknown", "x", {})


if __name__ == "__main__":
    unittest.main()
