def test_create_rule(client):
    resp = client.post("/api/v1/rules", json={
        "rule_name": "phone_rule",
        "match_type": "regex",
        "match_value": r"\d{3,}",
        "replace_strategy": "fixed",
        "replace_config": {"replacement": "***"},
        "priority": 10,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["rule_name"] == "phone_rule"
    assert data["match_type"] == "regex"
    assert data["enabled"] is True
    assert "id" in data


def test_create_rule_invalid_regex(client):
    resp = client.post("/api/v1/rules", json={
        "rule_name": "bad_regex",
        "match_type": "regex",
        "match_value": "[invalid",
        "replace_strategy": "fixed",
    })
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "VALIDATION_ERROR"
    assert "message" in body
    assert "details" in body


def test_create_rule_empty_match_value(client):
    resp = client.post("/api/v1/rules", json={
        "rule_name": "empty",
        "match_type": "exact",
        "match_value": "",
        "replace_strategy": "fixed",
    })
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "VALIDATION_ERROR"


def test_list_rules(client):
    client.post("/api/v1/rules", json={
        "rule_name": "r1",
        "match_type": "exact",
        "match_value": "a",
        "replace_strategy": "fixed",
    })
    client.post("/api/v1/rules", json={
        "rule_name": "r2",
        "match_type": "exact",
        "match_value": "b",
        "replace_strategy": "fixed",
    })
    resp = client.get("/api/v1/rules")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_get_rule_not_found(client):
    resp = client.get("/api/v1/rules/9999")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error_code"] == "NOT_FOUND"


def test_update_rule(client):
    create = client.post("/api/v1/rules", json={
        "rule_name": "original",
        "match_type": "exact",
        "match_value": "x",
        "replace_strategy": "fixed",
    })
    rule_id = create.json()["id"]
    resp = client.put(f"/api/v1/rules/{rule_id}", json={
        "rule_name": "updated",
    })
    assert resp.status_code == 200
    assert resp.json()["rule_name"] == "updated"


def test_toggle_rule_enabled(client):
    create = client.post("/api/v1/rules", json={
        "rule_name": "toggle",
        "match_type": "exact",
        "match_value": "x",
        "replace_strategy": "fixed",
    })
    rule_id = create.json()["id"]
    resp = client.patch(f"/api/v1/rules/{rule_id}/enabled", json={
        "enabled": False,
    })
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    resp2 = client.patch(f"/api/v1/rules/{rule_id}/enabled", json={
        "enabled": True,
    })
    assert resp2.json()["enabled"] is True


def test_update_priority(client):
    create = client.post("/api/v1/rules", json={
        "rule_name": "prio",
        "match_type": "exact",
        "match_value": "x",
        "replace_strategy": "fixed",
    })
    rule_id = create.json()["id"]
    resp = client.patch(f"/api/v1/rules/{rule_id}/priority", json={
        "priority": 5,
    })
    assert resp.status_code == 200
    assert resp.json()["priority"] == 5


def test_delete_rule(client):
    create = client.post("/api/v1/rules", json={
        "rule_name": "to_delete",
        "match_type": "exact",
        "match_value": "x",
        "replace_strategy": "fixed",
    })
    rule_id = create.json()["id"]
    resp = client.delete(f"/api/v1/rules/{rule_id}")
    assert resp.status_code == 204

    resp2 = client.get(f"/api/v1/rules/{rule_id}")
    assert resp2.status_code == 404


def test_delete_rule_not_found(client):
    resp = client.delete("/api/v1/rules/9999")
    assert resp.status_code == 404
