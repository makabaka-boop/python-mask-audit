def _create_rule(client, name="r", match_value="secret", enabled=True):
    resp = client.post("/api/v1/rules", json={
        "rule_name": name,
        "match_type": "exact",
        "match_value": match_value,
        "replace_strategy": "fixed",
        "replace_config": {"replacement": "***"},
        "enabled": enabled,
    })
    return resp.json()


def _create_sample(client, name="s1", raw_text="my secret data"):
    resp = client.post("/api/v1/samples", json={
        "sample_name": name,
        "raw_text": raw_text,
    })
    return resp.json()


def _create_group(client, name="g1"):
    resp = client.post("/api/v1/groups", json={"group_name": name})
    return resp.json()


def test_run_single_with_sample_id(client):
    rule = _create_rule(client)
    sample = _create_sample(client)
    resp = client.post("/api/v1/runs/single", json={
        "sample_id": sample["id"],
        "rule_id": rule["id"],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["output_text"] == "my *** data"
    assert data["hit_count"] == 1
    assert data["rule_id"] == rule["id"]
    assert data["sample_id"] == sample["id"]
    assert len(data["hit_details"]) == 1


def test_run_single_with_input_text(client):
    rule = _create_rule(client)
    resp = client.post("/api/v1/runs/single", json={
        "rule_id": rule["id"],
        "input_text": "the secret is here",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["output_text"] == "the *** is here"
    assert data["hit_count"] == 1


def test_run_single_disabled_rule(client):
    rule = _create_rule(client, enabled=False)
    resp = client.post("/api/v1/runs/single", json={
        "rule_id": rule["id"],
        "input_text": "secret",
    })
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "RULE_DISABLED"


def test_run_group_creates_snapshot(client):
    group = _create_group(client)
    sample = _create_sample(client)
    rule = _create_rule(client)
    client.post(f"/api/v1/groups/{group['id']}/rules", json={
        "group_id": group["id"],
        "rule_id": rule["id"],
    })
    resp = client.post("/api/v1/runs/group", json={
        "sample_id": sample["id"],
        "group_id": group["id"],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["group_id"] == group["id"]
    assert data["snapshot_id"] is not None
    assert data["hit_count"] == 1


def test_get_run_detail(client):
    rule = _create_rule(client)
    sample = _create_sample(client)
    run_resp = client.post("/api/v1/runs/single", json={
        "sample_id": sample["id"],
        "rule_id": rule["id"],
    })
    run_id = run_resp.json()["id"]
    resp = client.get(f"/api/v1/runs/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "hit_details" in data
    assert len(data["hit_details"]) == 1
    assert data["hit_details"][0]["matched_count"] == 1


def test_rule_stats(client):
    rule = _create_rule(client)
    sample = _create_sample(client)
    client.post("/api/v1/runs/single", json={
        "sample_id": sample["id"],
        "rule_id": rule["id"],
    })
    resp = client.get("/api/v1/runs/stats/rules")
    assert resp.status_code == 200
    stats = resp.json()
    assert len(stats) >= 1
    entry = next(s for s in stats if s["rule_id"] == rule["id"])
    assert entry["total_runs"] >= 1
    assert entry["total_hits"] >= 1


def test_get_run_not_found(client):
    resp = client.get("/api/v1/runs/9999")
    assert resp.status_code == 404
