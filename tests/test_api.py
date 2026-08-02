"""HTTP API 集成测试。"""


def _create_rule(client, **overrides):
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


def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_error_format(client):
    resp = client.get("/api/v1/rules/99999")
    assert resp.status_code == 404
    body = resp.get_json()
    assert set(body.keys()) == {"error_code", "message", "details"}
    assert body["error_code"] == "not_found"


def test_create_rule_regex_invalid(client):
    resp = client.post(
        "/api/v1/rules",
        json={
            "rule_name": "bad",
            "field_type": "x",
            "match_type": "regex",
            "match_value": "(",
            "replace_strategy": "fixed",
            "replace_config": {"replacement": "X"},
            "priority": 1,
            "enabled": True,
        },
    )
    assert resp.status_code == 400
    assert resp.get_json()["error_code"] == "regex_invalid"


def test_match_value_required(client):
    resp = client.post(
        "/api/v1/rules",
        json={
            "rule_name": "bad",
            "field_type": "x",
            "match_type": "exact",
            "match_value": "",
            "replace_strategy": "fixed",
            "replace_config": {"replacement": "X"},
            "priority": 1,
            "enabled": True,
        },
    )
    assert resp.status_code == 400
    assert resp.get_json()["error_code"] == "validation_error"


def test_rule_lifecycle_and_priority(client):
    rule = _create_rule(client)
    assert rule["enabled"] is True

    resp = client.post(f"/api/v1/rules/{rule['id']}/disable")
    assert resp.status_code == 200
    assert resp.get_json()["enabled"] is False

    resp = client.post(
        f"/api/v1/rules/{rule['id']}/priority", json={"priority": 1}
    )
    assert resp.status_code == 200
    assert resp.get_json()["priority"] == 1

    resp = client.post(f"/api/v1/rules/{rule['id']}/enable")
    assert resp.status_code == 200
    assert resp.get_json()["enabled"] is True


def test_single_run_and_snapshot_and_regression(client):
    rule = _create_rule(client)
    resp = client.post(
        "/api/v1/runs/single",
        json={"rule_id": rule["id"], "text": "call 13812345678 now"},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    run_id = body["run"]["id"]
    assert body["run"]["output_text"] == "call 138******78 now"
    assert body["run"]["hit_count"] == 1

    resp = client.get(f"/api/v1/runs/{run_id}/snapshot")
    assert resp.status_code == 200
    snaps = resp.get_json()["snapshots"]
    assert len(snaps) == 1
    assert snaps[0]["rule_name"] == "phone"

    resp = client.put(
        f"/api/v1/rules/{rule['id']}", json={"priority": 99}
    )
    assert resp.status_code == 200

    resp = client.get(f"/api/v1/regression?run_id={run_id}")
    assert resp.status_code == 200
    reg = resp.get_json()
    assert reg["has_baseline"] is True
    assert reg["baseline_run_id"] == run_id
    # 优先级变化应被归因到 priority_changed
    assert len(reg["change_categories"]["priority_changed"]) == 1
    assert reg["change_categories"]["priority_changed"][0]["rule_id"] == rule["id"]
    # 输出结果因为规则的执行顺序未变（只有一条规则），所以仍然一致
    assert reg["consistent"] is True


def test_preview_does_not_persist(client):
    rule = _create_rule(client)
    resp = client.post(
        f"/api/v1/preview/rule/{rule['id']}",
        json={"text": "call 13812345678 now"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["hit_count"] == 1

    resp = client.get("/api/v1/runs")
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 0


def test_group_run_and_disabled_rule_not_added(client):
    r1 = _create_rule(client, rule_name="r1", priority=10)
    r2 = _create_rule(
        client,
        rule_name="r2",
        match_type="exact",
        match_value="foo",
        replace_strategy="fixed",
        replace_config={"replacement": "BAR"},
        priority=20,
    )

    resp = client.post(
        "/api/v1/groups", json={"group_name": "g1", "description": "d"}
    )
    assert resp.status_code == 201
    group_id = resp.get_json()["id"]

    client.post(
        f"/api/v1/groups/{group_id}/rules", json={"rule_id": r1["id"]}
    )
    client.post(
        f"/api/v1/groups/{group_id}/rules", json={"rule_id": r2["id"]}
    )

    resp = client.post(
        "/api/v1/runs/group",
        json={"group_id": group_id, "text": "foo 13812345678"},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["run"]["hit_count"] == 2
    assert body["run"]["output_text"] == "BAR 138******78"

    client.post(f"/api/v1/rules/{r2['id']}/disable")
    resp = client.post(
        f"/api/v1/groups/{group_id}/rules", json={"rule_id": r2["id"]}
    )
    assert resp.status_code == 400
    assert resp.get_json()["error_code"] == "rule_disabled"


def test_stats(client):
    rule = _create_rule(client)
    client.post(
        "/api/v1/runs/single",
        json={"rule_id": rule["id"], "text": "13812345678 13900001111"},
    )
    resp = client.get("/api/v1/stats/hits")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_hit_count"] == 2
    assert data["rule_stats"][0]["hit_count"] == 2


def test_audit_events_recorded(client):
    _create_rule(client)
    resp = client.get("/api/v1/audit/events")
    assert resp.status_code == 200
    events = resp.get_json()["items"]
    assert any(e["event_type"] == "rule_created" for e in events)
