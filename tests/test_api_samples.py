def test_create_sample(client):
    resp = client.post("/api/v1/samples", json={
        "sample_name": "sample1",
        "sample_category": "phone",
        "raw_text": "call 123456",
        "expected_note": "mask phone",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["sample_name"] == "sample1"
    assert data["sample_category"] == "phone"
    assert data["raw_text"] == "call 123456"
    assert data["expected_note"] == "mask phone"
    assert "id" in data


def test_list_samples(client):
    client.post("/api/v1/samples", json={
        "sample_name": "s1",
        "raw_text": "text one",
    })
    client.post("/api/v1/samples", json={
        "sample_name": "s2",
        "raw_text": "text two",
    })
    resp = client.get("/api/v1/samples")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_get_sample(client):
    create = client.post("/api/v1/samples", json={
        "sample_name": "getme",
        "raw_text": "find me",
    })
    sample_id = create.json()["id"]
    resp = client.get(f"/api/v1/samples/{sample_id}")
    assert resp.status_code == 200
    assert resp.json()["sample_name"] == "getme"


def test_get_sample_not_found(client):
    resp = client.get("/api/v1/samples/9999")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "NOT_FOUND"


def test_update_sample(client):
    create = client.post("/api/v1/samples", json={
        "sample_name": "original",
        "raw_text": "old text",
    })
    sample_id = create.json()["id"]
    resp = client.put(f"/api/v1/samples/{sample_id}", json={
        "sample_name": "updated",
        "raw_text": "new text",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["sample_name"] == "updated"
    assert data["raw_text"] == "new text"


def test_delete_sample(client):
    create = client.post("/api/v1/samples", json={
        "sample_name": "todelete",
        "raw_text": "delete me",
    })
    sample_id = create.json()["id"]
    resp = client.delete(f"/api/v1/samples/{sample_id}")
    assert resp.status_code == 204

    resp2 = client.get(f"/api/v1/samples/{sample_id}")
    assert resp2.status_code == 404


def test_delete_sample_not_found(client):
    resp = client.delete("/api/v1/samples/9999")
    assert resp.status_code == 404
