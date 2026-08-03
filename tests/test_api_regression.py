def _setup_group_with_rule(client):
    group = client.post("/api/v1/groups", json={
        "group_name": "reg_group",
    }).json()
    sample = client.post("/api/v1/samples", json={
        "sample_name": "reg_sample",
        "raw_text": "hello secret world",
    }).json()
    rule = client.post("/api/v1/rules", json={
        "rule_name": "reg_rule",
        "match_type": "exact",
        "match_value": "secret",
        "replace_strategy": "fixed",
        "replace_config": {"replacement": "***"},
    }).json()
    client.post(f"/api/v1/groups/{group['id']}/rules", json={
        "group_id": group["id"],
        "rule_id": rule["id"],
    })
    return group, sample, rule


def test_regression_passed_after_run(client):
    group, sample, rule = _setup_group_with_rule(client)

    client.post("/api/v1/runs/group", json={
        "sample_id": sample["id"],
        "group_id": group["id"],
    })

    resp = client.get(f"/api/v1/regression/group/{group['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_passed"] is True
    assert data["rules_changed"] == []
    assert data["rules_added"] == []
    assert data["rules_removed"] == []
    assert rule["id"] in data["rules_unchanged"]


def test_regression_failed_after_rule_toggled_off(client):
    group, sample, rule = _setup_group_with_rule(client)

    client.post("/api/v1/runs/group", json={
        "sample_id": sample["id"],
        "group_id": group["id"],
    })

    client.patch(f"/api/v1/rules/{rule['id']}/enabled", json={
        "enabled": False,
    })

    resp = client.get(f"/api/v1/regression/group/{group['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_passed"] is False
    assert rule["id"] in data["rules_changed"]


def test_regression_no_snapshot(client):
    group = client.post("/api/v1/groups", json={
        "group_name": "no_snapshot_group",
    }).json()

    resp = client.get(f"/api/v1/regression/group/{group['id']}")
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "VALIDATION_ERROR"


def test_regression_group_not_found(client):
    resp = client.get("/api/v1/regression/group/9999")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "NOT_FOUND"
