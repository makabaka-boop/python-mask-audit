"""审计查询模块测试。"""
import pytest


def _make_rule(client, name="phone", **overrides):
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


def _make_sample(client, raw_text="phone 13800000000", name="s"):
    resp = client.post(
        "/api/v1/samples",
        json={
            "sample_name": name,
            "sample_category": "phone",
            "raw_text": raw_text,
            "expected_note": "",
        },
    )
    assert resp.status_code == 201
    return resp.get_json()


# ---------------------------------------------------------------------
# 审计事件写入
# ---------------------------------------------------------------------
def test_preview_writes_audit_but_no_run(client):
    rule = _make_rule(client)
    resp = client.post(
        f"/api/v1/preview/rule/{rule['id']}", json={"text": "13800000000"}
    )
    assert resp.status_code == 200

    runs = client.get("/api/v1/runs").get_json()
    assert runs["total"] == 0

    audit = client.get("/api/v1/audit/events").get_json()
    types = [e["event_type"] for e in audit["items"]]
    assert "preview_executed" in types


def test_group_preview_writes_audit_but_no_run(client):
    rule = _make_rule(client)
    group = _make_group(client)
    _add_rule(client, group["id"], rule["id"])
    resp = client.post(
        f"/api/v1/preview/group/{group['id']}", json={"text": "13800000000"}
    )
    assert resp.status_code == 200

    runs = client.get("/api/v1/runs").get_json()
    assert runs["total"] == 0

    audit = client.get("/api/v1/audit/events").get_json()
    previews = [
        e for e in audit["items"]
        if e["event_type"] == "preview_executed" and e["entity_type"] == "group"
    ]
    assert len(previews) >= 1


def test_regression_writes_audit_event(client):
    rule = _make_rule(client)
    group = _make_group(client)
    _add_rule(client, group["id"], rule["id"])
    sample = _make_sample(client)

    client.post(
        "/api/v1/runs/group",
        json={"group_id": group["id"], "sample_id": sample["id"]},
    )
    resp = client.get(f"/api/v1/regression?group_id={group['id']}")
    assert resp.status_code == 200

    audit = client.get("/api/v1/audit/events").get_json()
    types = [e["event_type"] for e in audit["items"]]
    assert "regression_executed" in types


def test_rule_enable_disable_priority_writes_audit(client):
    rule = _make_rule(client)
    client.post(f"/api/v1/rules/{rule['id']}/disable")
    client.post(f"/api/v1/rules/{rule['id']}/enable")
    client.post(f"/api/v1/rules/{rule['id']}/priority", json={"priority": 99})

    audit = client.get(f"/api/v1/audit/rules/{rule['id']}").get_json()
    event_types = [e["event_type"] for e in audit["recent_events"]]
    assert "rule_disabled" in event_types
    assert "rule_enabled" in event_types
    assert "rule_priority_changed" in event_types


def test_group_member_change_writes_audit(client):
    rule = _make_rule(client)
    group = _make_group(client)
    _add_rule(client, group["id"], rule["id"])
    client.delete(f"/api/v1/groups/{group['id']}/rules/{rule['id']}")

    audit = client.get(f"/api/v1/audit/groups/{group['id']}").get_json()
    event_types = [e["event_type"] for e in audit["recent_events"]]
    assert "group_rule_added" in event_types
    assert "group_rule_removed" in event_types


# ---------------------------------------------------------------------
# 规则维度聚合
# ---------------------------------------------------------------------
def test_audit_by_rule_config_versions_and_hits(client):
    rule = _make_rule(
        client,
        match_type="regex",
        match_value=r"1[3-9]\d{9}",
        replace_strategy="keep_edges",
        replace_config={"left": 3, "right": 2, "mask_char": "*"},
    )
    group = _make_group(client)
    _add_rule(client, group["id"], rule["id"])

    client.post(
        "/api/v1/runs/group",
        json={"group_id": group["id"], "text": "call 13812345678"},
    )
    client.put(
        f"/api/v1/rules/{rule['id']}",
        json={"replace_config": {"left": 4, "right": 4, "mask_char": "*"}},
    )
    client.post(
        "/api/v1/runs/group",
        json={"group_id": group["id"], "text": "call 13812345678"},
    )

    resp = client.get(f"/api/v1/audit/rules/{rule['id']}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["rule_id"] == rule["id"]
    assert body["current_config"]["priority"] == 10
    assert body["total_hit_count"] == 2
    assert body["run_count"] == 2
    assert body["last_hit_at"] is not None
    assert len(body["config_versions"]) == 2


# ---------------------------------------------------------------------
# 样例维度聚合
# ---------------------------------------------------------------------
def test_audit_by_sample_latest_run_and_distribution(client):
    r1 = _make_rule(client, name="r1", match_value="AAA",
                    replace_config={"replacement": "X"})
    r2 = _make_rule(client, name="r2", match_value="BBB",
                    replace_config={"replacement": "Y"})
    group = _make_group(client)
    _add_rule(client, group["id"], r1["id"])
    _add_rule(client, group["id"], r2["id"])
    sample = _make_sample(client, raw_text="AAA and BBB")

    client.post(
        "/api/v1/runs/group",
        json={"group_id": group["id"], "sample_id": sample["id"]},
    )

    resp = client.get(f"/api/v1/audit/samples/{sample['id']}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["sample"]["sample_name"] == "s"
    assert body["latest_run"] is not None
    assert body["latest_run"]["hit_count"] == 2
    assert body["latest_regression"]["consistent"] is True
    dist = {d["rule_id"]: d for d in body["rule_hit_distribution"]}
    assert r1["id"] in dist and r2["id"] in dist
    assert dist[r1["id"]]["total_hits"] == 1


# ---------------------------------------------------------------------
# 分组维度聚合
# ---------------------------------------------------------------------
def test_audit_by_group_member_change_summary(client):
    r1 = _make_rule(client, name="r1", match_value="AAA",
                    replace_config={"replacement": "X"})
    r2 = _make_rule(client, name="r2", match_value="BBB",
                    replace_config={"replacement": "Y"})
    group = _make_group(client)
    _add_rule(client, group["id"], r1["id"])

    client.post(
        "/api/v1/runs/group",
        json={"group_id": group["id"], "text": "AAA BBB"},
    )

    _add_rule(client, group["id"], r2["id"])
    client.delete(f"/api/v1/groups/{group['id']}/rules/{r1['id']}")

    resp = client.get(f"/api/v1/audit/groups/{group['id']}")
    assert resp.status_code == 200
    body = resp.get_json()
    current_ids = [m["rule_id"] for m in body["current_members"]]
    assert r2["id"] in current_ids
    assert r1["id"] not in current_ids
    assert len(body["snapshot_members"]) >= 1
    changes = body["member_change_summary"]
    event_types = [c["event_type"] for c in changes]
    assert "group_rule_added" in event_types
    assert "group_rule_removed" in event_types
