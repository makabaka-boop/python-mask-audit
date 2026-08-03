def test_preview_returns_result_without_run(client):
    rule_resp = client.post("/api/v1/rules", json={
        "rule_name": "preview_rule",
        "match_type": "exact",
        "match_value": "secret",
        "replace_strategy": "fixed",
        "replace_config": {"replacement": "***"},
    })
    rule_id = rule_resp.json()["id"]

    resp = client.post("/api/v1/preview", json={
        "rule_id": rule_id,
        "input_text": "my secret text",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["output_text"] == "my *** text"
    assert data["hit_count"] == 1
    assert data["rule_id"] == rule_id

    runs_resp = client.get("/api/v1/runs")
    assert runs_resp.status_code == 200
    assert runs_resp.json() == []


def test_preview_with_sample_id(client):
    rule_resp = client.post("/api/v1/rules", json={
        "rule_name": "preview_rule2",
        "match_type": "exact",
        "match_value": "data",
        "replace_strategy": "fixed",
        "replace_config": {"replacement": "###"},
    })
    rule_id = rule_resp.json()["id"]

    sample_resp = client.post("/api/v1/samples", json={
        "sample_name": "s1",
        "raw_text": "raw data here",
    })
    sample_id = sample_resp.json()["id"]

    resp = client.post("/api/v1/preview", json={
        "rule_id": rule_id,
        "sample_id": sample_id,
    })
    assert resp.status_code == 200
    assert resp.json()["output_text"] == "raw ### here"


def test_preview_disabled_rule(client):
    rule_resp = client.post("/api/v1/rules", json={
        "rule_name": "disabled_preview",
        "match_type": "exact",
        "match_value": "secret",
        "replace_strategy": "fixed",
        "replace_config": {"replacement": "***"},
        "enabled": False,
    })
    rule_id = rule_resp.json()["id"]

    resp = client.post("/api/v1/preview", json={
        "rule_id": rule_id,
        "input_text": "secret",
    })
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "RULE_DISABLED"


def test_preview_rule_not_found(client):
    resp = client.post("/api/v1/preview", json={
        "rule_id": 9999,
        "input_text": "text",
    })
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "NOT_FOUND"
