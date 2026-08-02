"""冲突检测与回归验证 HTTP API 测试。"""
import pytest


def _make_rule(client, name, **overrides):
    payload = {
        "rule_name": name,
        "field_type": "phone",
        "match_type": "exact",
        "match_value": "13800000000",
        "replace_strategy": "fixed",
        "replace_config": {"replacement": "X"},
        "priority": 10,
        "enabled": True,
    }
    payload.update(overrides)
    resp = client.post("/api/v1/rules", json=payload)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def _make_group(client, name="g"):
    resp = client.post(
        "/api/v1/groups", json={"group_name": name, "description": "d"}
    )
    assert resp.status_code == 201
    return resp.get_json()


def _add_rule(client, group_id, rule_id):
    resp = client.post(
        f"/api/v1/groups/{group_id}/rules", json={"rule_id": rule_id}
    )
    assert resp.status_code == 200, resp.get_json()
    return resp


def _make_sample(client, raw_text="phone 13800000000"):
    resp = client.post(
        "/api/v1/samples",
        json={
            "sample_name": "s1",
            "sample_category": "phone",
            "raw_text": raw_text,
            "expected_note": "",
        },
    )
    assert resp.status_code == 201
    return resp.get_json()


# ---------------------------------------------------------------------
# 冲突检测接口
# ---------------------------------------------------------------------
def test_conflict_api_duplicate_exact(client):
    r1 = _make_rule(client, "r1", match_value="111")
    r2 = _make_rule(client, "r2", match_value="111")
    g = _make_group(client)
    _add_rule(client, g["id"], r1["id"])
    _add_rule(client, g["id"], r2["id"])

    resp = client.get(f"/api/v1/groups/{g['id']}/conflicts")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["conflict_count"] >= 1
    types = [c["conflict_type"] for c in body["conflicts"]]
    assert "duplicate_exact" in types


def test_conflict_api_contains_overlap(client):
    r1 = _make_rule(
        client,
        "outer",
        match_type="contains",
        match_value="top secret",
    )
    r2 = _make_rule(
        client,
        "inner",
        match_type="contains",
        match_value="secret",
    )
    g = _make_group(client)
    _add_rule(client, g["id"], r1["id"])
    _add_rule(client, g["id"], r2["id"])

    resp = client.get(f"/api/v1/groups/{g['id']}/conflicts")
    assert resp.status_code == 200
    types = [c["conflict_type"] for c in resp.get_json()["conflicts"]]
    assert "contains_overlap" in types


def test_conflict_api_same_priority_diff(client):
    r1 = _make_rule(
        client, "a", match_value="1", priority=5,
        replace_config={"replacement": "X"},
    )
    r2 = _make_rule(
        client, "b", match_value="2", priority=5,
        replace_config={"replacement": "Y"},
    )
    g = _make_group(client)
    _add_rule(client, g["id"], r1["id"])
    _add_rule(client, g["id"], r2["id"])

    resp = client.get(f"/api/v1/groups/{g['id']}/conflicts")
    assert resp.status_code == 200
    types = [c["conflict_type"] for c in resp.get_json()["conflicts"]]
    assert "same_priority_diff" in types


def test_conflict_does_not_block_execution(client):
    """冲突只返回提示，不阻断加入分组或演练执行。"""
    r1 = _make_rule(client, "r1", match_value="111")
    r2 = _make_rule(client, "r2", match_value="111")
    g = _make_group(client)
    _add_rule(client, g["id"], r1["id"])
    _add_rule(client, g["id"], r2["id"])

    conflicts = client.get(f"/api/v1/groups/{g['id']}/conflicts").get_json()
    assert conflicts["conflict_count"] >= 1

    resp = client.post(
        "/api/v1/runs/group",
        json={"group_id": g["id"], "text": "value 111"},
    )
    assert resp.status_code == 201
    assert resp.get_json()["run"]["hit_count"] >= 1


# ---------------------------------------------------------------------
# 回归验证
# ---------------------------------------------------------------------
def test_regression_consistent_when_no_change(client):
    r = _make_rule(client, "phone", match_value="13800000000")
    g = _make_group(client)
    _add_rule(client, g["id"], r["id"])
    sample = _make_sample(client, "call 13800000000 now")

    resp = client.post(
        "/api/v1/runs/group",
        json={"group_id": g["id"], "sample_id": sample["id"]},
    )
    assert resp.status_code == 201
    run_id = resp.get_json()["run"]["id"]

    resp = client.get(f"/api/v1/regression?run_id={run_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["has_baseline"] is True
    assert body["consistent"] is True
    assert body["baseline_output"] == body["current_output"]
    assert body["snapshot_diff"] == []


def test_regression_inconsistent_when_replace_config_changed(client):
    r = _make_rule(
        client,
        "phone",
        match_value="13800000000",
        replace_config={"replacement": "FIRST"},
    )
    g = _make_group(client)
    _add_rule(client, g["id"], r["id"])
    sample = _make_sample(client, "call 13800000000 now")

    resp = client.post(
        "/api/v1/runs/group",
        json={"group_id": g["id"], "sample_id": sample["id"]},
    )
    run_id = resp.get_json()["run"]["id"]

    client.put(
        f"/api/v1/rules/{r['id']}",
        json={"replace_config": {"replacement": "SECOND"}},
    )

    resp = client.get(f"/api/v1/regression?run_id={run_id}")
    body = resp.get_json()
    assert body["consistent"] is False
    assert body["baseline_output"] != body["current_output"]
    cats = body["change_categories"]
    assert len(cats["replace_config_changed"]) == 1
    assert cats["replace_config_changed"][0]["rule_id"] == r["id"]
    diff_types = [d["change_type"] for d in body["snapshot_diff"]]
    assert "modified" in diff_types


def test_regression_membership_change(client):
    r1 = _make_rule(client, "r1", match_value="AAA",
                    replace_config={"replacement": "X"})
    r2 = _make_rule(client, "r2", match_value="BBB",
                    replace_config={"replacement": "Y"})
    g = _make_group(client)
    _add_rule(client, g["id"], r1["id"])
    sample = _make_sample(client, "AAA and BBB")

    resp = client.post(
        "/api/v1/runs/group",
        json={"group_id": g["id"], "sample_id": sample["id"]},
    )
    run_id = resp.get_json()["run"]["id"]
    assert "BBB" in resp.get_json()["run"]["output_text"]

    _add_rule(client, g["id"], r2["id"])

    resp = client.get(f"/api/v1/regression?run_id={run_id}")
    body = resp.get_json()
    assert body["consistent"] is False
    assert any(
        c["change"] == "added" and c["rule_id"] == r2["id"]
        for c in body["change_categories"]["membership_changed"]
    )


def test_regression_priority_change_detected(client):
    r1 = _make_rule(
        client,
        "a_to_x",
        match_value="A",
        replace_config={"replacement": "X"},
        priority=10,
    )
    r2 = _make_rule(
        client,
        "x_to_y",
        match_value="X",
        replace_config={"replacement": "Y"},
        priority=20,
    )
    g = _make_group(client)
    _add_rule(client, g["id"], r1["id"])
    _add_rule(client, g["id"], r2["id"])
    sample = _make_sample(client, "A")

    resp = client.post(
        "/api/v1/runs/group",
        json={"group_id": g["id"], "sample_id": sample["id"]},
    )
    run_id = resp.get_json()["run"]["id"]

    client.post(f"/api/v1/rules/{r2['id']}/priority", json={"priority": 5})

    resp = client.get(f"/api/v1/regression?run_id={run_id}")
    body = resp.get_json()
    assert body["change_categories"]["priority_changed"]
    pri = body["change_categories"]["priority_changed"][0]
    assert pri["rule_id"] == r2["id"]
    assert pri["snapshot_priority"] == 20
    assert pri["current_priority"] == 5


def test_regression_uses_snapshot_not_current_text_only(client):
    """快照必须参与重放：即使baseline文本和current文本相同，
    也必须能识别规则配置变化。"""
    r = _make_rule(
        client,
        "phone",
        match_type="regex",
        match_value=r"1[3-9]\d{9}",
        replace_strategy="keep_edges",
        replace_config={"left": 3, "right": 2, "mask_char": "*"},
    )
    g = _make_group(client)
    _add_rule(client, g["id"], r["id"])
    sample = _make_sample(client, "call 13812345678")

    resp = client.post(
        "/api/v1/runs/group",
        json={"group_id": g["id"], "sample_id": sample["id"]},
    )
    run_id = resp.get_json()["run"]["id"]
    assert resp.get_json()["run"]["output_text"] == "call 138******78"

    client.put(
        f"/api/v1/rules/{r['id']}",
        json={"replace_config": {"left": 0, "right": 0, "mask_char": "*"}},
    )

    resp = client.get(f"/api/v1/regression?run_id={run_id}")
    body = resp.get_json()
    assert body["consistent"] is False
    assert body["baseline_output"] == "call 138******78"
    assert body["current_output"] == "call ***********"
    assert body["change_categories"]["replace_config_changed"]
