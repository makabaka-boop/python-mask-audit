from app.services.executor import RuleExecutor


def test_execute_single_exact_match():
    rule = {
        "id": 1,
        "match_type": "exact",
        "match_value": "hello",
        "replace_strategy": "fixed",
        "replace_config": {"replacement": "***"},
    }
    result = RuleExecutor.execute_single("say hello", rule)
    assert result["output_text"] == "say ***"
    assert result["hit_count"] == 1
    assert len(result["hit_details"]) == 1
    assert result["hit_details"][0]["matched_count"] == 1
    assert result["hit_details"][0]["before_fragment"] == "hello"
    assert result["hit_details"][0]["after_fragment"] == "***"


def test_execute_single_regex_multiple_hits():
    rule = {
        "id": 2,
        "match_type": "regex",
        "match_value": r"\d+",
        "replace_strategy": "fixed",
        "replace_config": {"replacement": "#"},
    }
    result = RuleExecutor.execute_single("a1b2c3", rule)
    assert result["output_text"] == "a#b#c#"
    assert result["hit_count"] == 3
    assert result["hit_details"][0]["matched_count"] == 3


def test_execute_single_no_matches():
    rule = {
        "id": 3,
        "match_type": "exact",
        "match_value": "zzz",
        "replace_strategy": "fixed",
        "replace_config": {"replacement": "***"},
    }
    result = RuleExecutor.execute_single("no match here", rule)
    assert result["output_text"] == "no match here"
    assert result["hit_count"] == 0
    assert result["hit_details"] == []


def test_execute_group_priority_order():
    rules = [
        {
            "id": 1,
            "match_type": "exact",
            "match_value": "cat",
            "replace_strategy": "fixed",
            "replace_config": {"replacement": "dog"},
            "priority": 1,
            "enabled": True,
        },
        {
            "id": 2,
            "match_type": "exact",
            "match_value": "dog",
            "replace_strategy": "fixed",
            "replace_config": {"replacement": "bird"},
            "priority": 2,
            "enabled": True,
        },
    ]
    result = RuleExecutor.execute_group("cat", rules)
    assert result["output_text"] == "bird"
    assert result["hit_count"] == 2


def test_execute_group_skips_disabled():
    rules = [
        {
            "id": 1,
            "match_type": "exact",
            "match_value": "secret",
            "replace_strategy": "fixed",
            "replace_config": {"replacement": "***"},
            "priority": 1,
            "enabled": False,
        },
        {
            "id": 2,
            "match_type": "exact",
            "match_value": "data",
            "replace_strategy": "fixed",
            "replace_config": {"replacement": "###"},
            "priority": 2,
            "enabled": True,
        },
    ]
    result = RuleExecutor.execute_group("secret data", rules)
    assert result["output_text"] == "secret ###"
    assert result["hit_count"] == 1


def test_execute_single_idempotent():
    rule = {
        "id": 4,
        "match_type": "regex",
        "match_value": r"[a-z]+",
        "replace_strategy": "middle_mask",
        "replace_config": {},
    }
    first = RuleExecutor.execute_single("hello world", rule)
    second = RuleExecutor.execute_single(first["output_text"], rule)
    assert second["output_text"] == first["output_text"]


def test_execute_single_replace_config_string():
    rule = {
        "id": 5,
        "match_type": "exact",
        "match_value": "x",
        "replace_strategy": "fixed",
        "replace_config": '{"replacement": "Y"}',
    }
    result = RuleExecutor.execute_single("x", rule)
    assert result["output_text"] == "Y"
