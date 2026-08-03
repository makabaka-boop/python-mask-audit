import pytest

from app.services.replacer import (
    apply_replace,
    fixed_replace,
    keep_edges_replace,
    middle_mask_replace,
)


def test_fixed_replace_basic():
    assert fixed_replace("hello", {"replacement": "***"}) == "***"


def test_fixed_replace_default():
    assert fixed_replace("anything", {}) == "***"


def test_keep_edges_normal():
    result = keep_edges_replace("1234567890", {"left": 2, "right": 2})
    assert result == "12******90"


def test_keep_edges_len_le_left():
    result = keep_edges_replace("ab", {"left": 3, "right": 1})
    assert result == "a*"


def test_keep_edges_len_le_left_plus_right():
    result = keep_edges_replace("abc", {"left": 2, "right": 2})
    assert result == "ab*"


def test_keep_edges_single_char():
    result = keep_edges_replace("a", {"left": 1, "right": 1})
    assert result == "a"


def test_keep_edges_idempotent():
    config = {"left": 2, "right": 2}
    once = keep_edges_replace("1234567890", config)
    twice = keep_edges_replace(once, config)
    assert twice == once


def test_middle_mask_one_char_unchanged():
    assert middle_mask_replace("a", {}) == "a"


def test_middle_mask_two_chars_unchanged():
    assert middle_mask_replace("ab", {}) == "ab"


def test_middle_mask_three_chars():
    assert middle_mask_replace("abc", {}) == "a*c"


def test_middle_mask_four_chars():
    assert middle_mask_replace("abcd", {}) == "a**d"


def test_middle_mask_five_plus_chars():
    assert middle_mask_replace("abcde", {}) == "a***e"


def test_middle_mask_idempotent():
    once = middle_mask_replace("hello", {})
    twice = middle_mask_replace(once, {})
    assert twice == once


def test_apply_replace_unknown_strategy_raises():
    with pytest.raises(ValueError):
        apply_replace("unknown", "text", {})
