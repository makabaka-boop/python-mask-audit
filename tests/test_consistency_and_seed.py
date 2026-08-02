"""一致性自检与初始化数据测试。"""
import os
import sys
import tempfile

import pytest


sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def _make_rule(client, **overrides):
    payload = {
        "rule_name": "phone",
        "field_type": "phone",
        "match_type": "regex",
        "match_value": r"1[3-9]\d{9}",
        "replace_strategy": "keep_edges",
        "replace_config": {"left": 3, "right": 2, "mask_char": "*"},
        "priority": 10,
        "enabled": True,
    }
    payload.update(overrides)
    resp = client.post("/api/v1/rules", json=payload)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def _make_group(client):
    resp = client.post(
        "/api/v1/groups", json={"group_name": "g", "description": ""}
    )
    assert resp.status_code == 201
    return resp.get_json()


def _make_sample(client, text="call 13812345678"):
    resp = client.post(
        "/api/v1/samples",
        json={"sample_name": "s", "raw_text": text, "sample_category": "phone"},
    )
    assert resp.status_code == 201
    return resp.get_json()


# ---------------------------------------------------------------------
# 自检通过
# ---------------------------------------------------------------------
def test_consistency_checks_pass_after_clean_workflow(client):
    rule = _make_rule(client)
    group = _make_group(client)
    sample = _make_sample(client)
    client.post(
        f"/api/v1/groups/{group['id']}/rules", json={"rule_id": rule["id"]}
    )
    client.post(
        "/api/v1/runs/group",
        json={"group_id": group["id"], "sample_id": sample["id"]},
    )

    resp = client.get("/api/v1/consistency/checks")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["all_passed"] is True
    assert body["total_issue_count"] == 0
    check_names = {c["name"] for c in body["checks"]}
    assert {
        "orphan_hit_details",
        "group_run_without_snapshot",
        "snapshot_hit_mismatch",
        "preview_persisted",
        "disabled_rule_in_run",
        "invalid_regex_residue",
        "regression_no_baseline",
    }.issubset(check_names)
    for c in body["checks"]:
        assert c["passed"] is True
        assert c["issue_count"] == 0


# ---------------------------------------------------------------------
# 自检异常：缺少快照、禁用规则、非法正则残留、无基准
# ---------------------------------------------------------------------
def test_consistency_detects_group_run_without_snapshot(app, client):
    """直接插入一条没有快照的分组演练，自检应发现。"""
    with app.app_context():
        from app.database import get_db

        db = get_db()
        cur = db.execute(
            """
            INSERT INTO groups (group_name) VALUES ('gx')
            """
        )
        group_id = cur.lastrowid
        db.execute(
            """
            INSERT INTO runs (group_id, input_text, output_text, hit_count)
            VALUES (?, '', '', 0)
            """,
            (group_id,),
        )
        db.commit()

    resp = client.get("/api/v1/consistency/checks")
    body = resp.get_json()
    assert body["all_passed"] is False
    check = next(
        c for c in body["checks"] if c["name"] == "group_run_without_snapshot"
    )
    assert check["passed"] is False
    assert check["issue_count"] >= 1


def test_consistency_detects_disabled_rule_in_run(client):
    """把参与演练的规则禁用，再手动让快照显示 enabled=0。"""
    rule = _make_rule(client)
    group = _make_group(client)
    sample = _make_sample(client)
    client.post(
        f"/api/v1/groups/{group['id']}/rules", json={"rule_id": rule["id"]}
    )
    client.post(
        "/api/v1/runs/group",
        json={"group_id": group["id"], "sample_id": sample["id"]},
    )
    client.post(f"/api/v1/rules/{rule['id']}/disable")

    # 直接将该规则最近一次快照标记为 enabled=0 模拟历史异常
    client.application
    with client.application.app_context():
        from app.database import get_db

        db = get_db()
        db.execute(
            "UPDATE rule_snapshots SET enabled = 0 WHERE rule_id = ?",
            (rule["id"],),
        )
        db.commit()

    resp = client.get("/api/v1/consistency/checks")
    body = resp.get_json()
    check = next(
        c for c in body["checks"] if c["name"] == "disabled_rule_in_run"
    )
    assert check["passed"] is False
    assert check["issue_count"] >= 1


def test_consistency_detects_invalid_regex(app, client):
    """直接插入一条非法正则规则，绕过入库校验。"""
    with app.app_context():
        from app.database import get_db

        db = get_db()
        db.execute(
            """
            INSERT INTO rules (rule_name, field_type, match_type, match_value,
                               replace_strategy, replace_config, priority, enabled)
            VALUES ('bad', 'x', 'regex', '(', 'fixed', '{}', 1, 1)
            """
        )
        db.commit()

    resp = client.get("/api/v1/consistency/checks")
    body = resp.get_json()
    check = next(
        c for c in body["checks"] if c["name"] == "invalid_regex_residue"
    )
    assert check["passed"] is False
    assert check["issue_count"] >= 1
    assert check["details"][0]["match_value"] == "("


def test_consistency_detects_regression_no_baseline(client):
    """只建分组和样例不演练，应报缺少基准。"""
    _make_group(client)
    _make_sample(client)

    resp = client.get("/api/v1/consistency/checks")
    body = resp.get_json()
    check = next(
        c for c in body["checks"] if c["name"] == "regression_no_baseline"
    )
    assert check["passed"] is False
    assert check["issue_count"] >= 2


# ---------------------------------------------------------------------
# 预览不落库（preview_persisted 检查）
# ---------------------------------------------------------------------
def test_consistency_preview_not_persisted(client):
    rule = _make_rule(client)
    client.post(
        f"/api/v1/preview/rule/{rule['id']}", json={"text": "13812345678"}
    )
    resp = client.get("/api/v1/consistency/checks")
    body = resp.get_json()
    check = next(
        c for c in body["checks"] if c["name"] == "preview_persisted"
    )
    assert check["passed"] is True
    assert check["issue_count"] == 0


# ---------------------------------------------------------------------
# 初始化数据脚本
# ---------------------------------------------------------------------
def test_seed_data_script_creates_full_chain():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.environ["MASK_AUDIT_DB"] = db_path
    os.environ["MASK_AUDIT_PORT"] = "0"
    try:
        from scripts import seed_data

        result = seed_data.seed()
        assert len(result["rule_ids"]) >= 3
        assert result["group_id"] > 0
        assert len(result["sample_ids"]) >= 1
        assert result["run_id"] > 0
        assert "***" in result["output_text"] or "*" in result["output_text"]

        from app.main import create_app

        app = create_app()
        with app.app_context():
            from app.consistency import run_all_checks

            report = run_all_checks()
            assert report["all_passed"] is True, report
    finally:
        os.close(db_fd)
        os.unlink(db_path)
        os.environ.pop("MASK_AUDIT_DB", None)


# ---------------------------------------------------------------------
# 所有新增接口保持 /api/v1 前缀
# ---------------------------------------------------------------------
def test_all_new_endpoints_use_api_v1_prefix(app):
    """通过 url_map 验证所有新增接口都已注册且以 /api/v1 开头。"""
    with app.app_context():
        rules = [
            r.rule
            for r in app.url_map.iter_rules()
            if not r.rule.startswith("/static")
        ]
    expected = {
        "/api/v1/consistency/checks",
        "/api/v1/audit/events",
        "/api/v1/audit/rules/<int:rule_id>",
        "/api/v1/audit/samples/<int:sample_id>",
        "/api/v1/audit/groups/<int:group_id>",
        "/api/v1/groups/<int:group_id>/conflicts",
        "/api/v1/regression",
        "/api/v1/preview/rule/<int:rule_id>",
        "/api/v1/preview/group/<int:group_id>",
    }
    for path in expected:
        assert path in rules, f"{path} 未注册"
    # 所有业务接口必须以 /api/v1 开头
    for rule in rules:
        if rule == "/":
            continue
        assert rule.startswith("/api/v1"), f"{rule} 未使用 /api/v1 前缀"
