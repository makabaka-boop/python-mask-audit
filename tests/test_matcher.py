import pytest

from app.services.matcher import find_matches


def test_exact_match_single():
    result = find_matches("exact", "hello", "say hello world")
    assert result == [(4, 9, "hello")]


def test_exact_match_multiple():
    result = find_matches("exact", "ab", "ab ab ab")
    assert result == [(0, 2, "ab"), (3, 5, "ab"), (6, 8, "ab")]


def test_contains_same_as_exact():
    text = "say hello world"
    exact_result = find_matches("exact", "hello", text)
    contains_result = find_matches("contains", "hello", text)
    assert contains_result == exact_result


def test_regex_match_groups():
    result = find_matches("regex", r"\d+", "abc123def456")
    assert result == [(3, 6, "123"), (9, 12, "456")]


def test_regex_match_single():
    result = find_matches("regex", r"world", "hello world")
    assert result == [(6, 11, "world")]


def test_invalid_regex_raises():
    with pytest.raises(ValueError):
        find_matches("regex", "[invalid", "text")


def test_unknown_match_type_raises():
    with pytest.raises(ValueError):
        find_matches("unknown", "x", "text")


def test_empty_match_value_returns_empty():
    result = find_matches("exact", "", "some text")
    assert result == []


def test_empty_match_value_contains_returns_empty():
    result = find_matches("contains", "", "some text")
    assert result == []


def test_exact_match_no_occurrence():
    result = find_matches("exact", "xyz", "abc def")
    assert result == []
