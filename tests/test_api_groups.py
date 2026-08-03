import pytest


def _create_rule(client, name="r", match_value="x", enabled=True, priority=100):
    resp = client.post("/api/v1/rules", json={
        "rule_name": name,
        "match_type": "exact",
        "match_value": match_value,
        "replace_strategy": "fixed",
        "replace_config": {"replacement": "***"},
        "enabled": enabled,
        "priority": priority,
    })
    return resp.json()


def _create_group(client, name="g1"):
    resp = client.post("/api/v1/groups", json={"group_name": name})
    return resp.json()


def test_create_group(client):
    resp = client.post("/api/v1/groups", json={
        "group_name": "test_group",
        "description": "desc",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["group_name"] == "test_group"
    assert data["description"] == "desc"
    assert "id" in data


def test_add_rule_to_group(client):
    group = _create_group(client)
    rule = _create_rule(client)
    resp = client.post(f"/api/v1/groups/{group['id']}/rules", json={
        "group_id": group["id"],
        "rule_id": rule["id"],
    })
    assert resp.status_code == 201
    assert resp.json()["rule_id"] == rule["id"]


def test_add_duplicate_rule_conflict(client):
    group = _create_group(client)
    rule = _create_rule(client)
    client.post(f"/api/v1/groups/{group['id']}/rules", json={
        "group_id": group["id"],
        "rule_id": rule["id"],
    })
    resp = client.post(f"/api/v1/groups/{group['id']}/rules", json={
        "group_id": group["id"],
        "rule_id": rule["id"],
    })
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "CONFLICT"


def test_remove_rule_from_group(client):
    group = _create_group(client)
    rule = _create_rule(client)
    client.post(f"/api/v1/groups/{group['id']}/rules", json={
        "group_id": group["id"],
        "rule_id": rule["id"],
    })
    resp = client.delete(f"/api/v1/groups/{group['id']}/rules/{rule['id']}")
    assert resp.status_code == 204


def test_get_group_with_rules(client):
    group = _create_group(client)
    rule = _create_rule(client, name="myrule")
    client.post(f"/api/v1/groups/{group['id']}/rules", json={
        "group_id": group["id"],
        "rule_id": rule["id"],
    })
    resp = client.get(f"/api/v1/groups/{group['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == group["id"]
    assert len(data["rules"]) == 1
    assert data["rules"][0]["rule_name"] == "myrule"


def test_list_group_rules_enabled_only(client):
    group = _create_group(client)
    rule_on = _create_rule(client, name="on", enabled=True)
    rule_off = _create_rule(client, name="off", enabled=False)
    client.post(f"/api/v1/groups/{group['id']}/rules", json={
        "group_id": group["id"],
        "rule_id": rule_on["id"],
    })
    client.post(f"/api/v1/groups/{group['id']}/rules", json={
        "group_id": group["id"],
        "rule_id": rule_off["id"],
    })

    resp_all = client.get(f"/api/v1/groups/{group['id']}/rules")
    assert len(resp_all.json()) == 2

    resp_enabled = client.get(
        f"/api/v1/groups/{group['id']}/rules?enabled_only=true"
    )
    enabled_rules = resp_enabled.json()
    assert len(enabled_rules) == 1
    assert enabled_rules[0]["enabled"] is True


def test_get_group_not_found(client):
    resp = client.get("/api/v1/groups/9999")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "NOT_FOUND"
