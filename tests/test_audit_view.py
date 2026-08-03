from __future__ import annotations
"""审计查询模块测试。"""
import pytest


def _create_rule(client, **overrides):
    payload = {
        "rule_name": "test_rule",
        "match_type": "exact",
        "match_value": "SECRET",
        "replace_strategy": "fixed",
        "replace_config": {"replacement": "***"},
        "priority": 100,
        "field_type": "text",
        "enabled": True,
    }
    payload.update(overrides)
    resp = client.post("/api/v1/rules", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_group(client, name="g1"):
    return client.post("/api/v1/groups", json={"group_name": name}).json()


def _create_sample(client, name="s1", text="hello SECRET world"):
    return client.post("/api/v1/samples", json={
        "sample_name": name, "raw_text": text
    }).json()


def _add_to_group(client, group_id, rule_id):
    return client.post(f"/api/v1/groups/{group_id}/rules",
                       json={"group_id": group_id, "rule_id": rule_id})


def _run_group(client, sample_id, group_id):
    return client.post("/api/v1/runs/group",
                       json={"sample_id": sample_id, "group_id": group_id}).json()


class TestAuditEventWriting:

    def test_rule_create_writes_audit(self, client):
        r = _create_rule(client, rule_name="audit_rule")
        events = client.get("/api/v1/audit/events",
                            params={"event_type": "RULE_CREATE"}).json()
        assert len(events) >= 1
        assert any(e["target_id"] == r["id"] for e in events)

    def test_rule_toggle_writes_audit(self, client):
        r = _create_rule(client)
        client.patch(f"/api/v1/rules/{r['id']}/enabled", json={"enabled": False})
        events = client.get("/api/v1/audit/events",
                            params={"event_type": "RULE_DISABLE",
                                    "target_id": r["id"]}).json()
        assert len(events) >= 1

    def test_priority_change_writes_audit(self, client):
        r = _create_rule(client)
        client.patch(f"/api/v1/rules/{r['id']}/priority", json={"priority": 5})
        events = client.get("/api/v1/audit/events",
                            params={"event_type": "RULE_PRIORITY",
                                    "target_id": r["id"]}).json()
        assert len(events) >= 1

    def test_group_member_add_writes_audit(self, client):
        r = _create_rule(client)
        g = _create_group(client)
        _add_to_group(client, g["id"], r["id"])
        events = client.get("/api/v1/audit/events",
                            params={"event_type": "GROUP_ADD_RULE",
                                    "target_id": g["id"]}).json()
        assert len(events) >= 1

    def test_group_member_remove_writes_audit(self, client):
        r = _create_rule(client)
        g = _create_group(client)
        _add_to_group(client, g["id"], r["id"])
        client.delete(f"/api/v1/groups/{g['id']}/rules/{r['id']}")
        events = client.get("/api/v1/audit/events",
                            params={"event_type": "GROUP_REMOVE_RULE",
                                    "target_id": g["id"]}).json()
        assert len(events) >= 1

    def test_run_single_writes_audit(self, client):
        r = _create_rule(client)
        resp = client.post("/api/v1/runs/single",
                           json={"rule_id": r["id"], "input_text": "SECRET"})
        assert resp.status_code == 201
        events = client.get("/api/v1/audit/events",
                            params={"event_type": "RUN_SINGLE"}).json()
        assert len(events) >= 1

    def test_run_group_writes_audit(self, client):
        r = _create_rule(client)
        g = _create_group(client)
        s = _create_sample(client)
        _add_to_group(client, g["id"], r["id"])
        _run_group(client, s["id"], g["id"])
        events = client.get("/api/v1/audit/events",
                            params={"event_type": "RUN_GROUP"}).json()
        assert len(events) >= 1

    def test_regression_writes_audit(self, client):
        r = _create_rule(client)
        g = _create_group(client)
        s = _create_sample(client)
        _add_to_group(client, g["id"], r["id"])
        _run_group(client, s["id"], g["id"])
        client.get(f"/api/v1/regression/group/{g['id']}")
        events = client.get("/api/v1/audit/events",
                            params={"event_type": "REGRESSION"}).json()
        assert len(events) >= 1

    def test_preview_writes_audit_but_not_run_record(self, client):
        r = _create_rule(client)
        resp = client.post("/api/v1/preview",
                           json={"rule_id": r["id"], "input_text": "SECRET"})
        assert resp.status_code == 200

        events = client.get("/api/v1/audit/events",
                            params={"event_type": "PREVIEW",
                                    "target_id": r["id"]}).json()
        assert len(events) >= 1

        runs = client.get("/api/v1/runs", params={"rule_id": r["id"]}).json()
        assert len(runs) == 0

        hit_details_count = client.get(
            "/api/v1/audit/events",
            params={"event_type": "PREVIEW", "target_id": r["id"]}
        ).json()
        assert hit_details_count[0]["detail"]["hit_count"] >= 0


class TestRuleAuditView:

    def test_rule_view_returns_current_config(self, client):
        r = _create_rule(client, rule_name="view_rule")
        resp = client.get(f"/api/v1/audit/rules/{r['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["rule_id"] == r["id"]
        assert data["current_config"]["rule_name"] == "view_rule"

    def test_rule_view_config_versions_from_snapshots(self, client):
        r = _create_rule(client, match_value="V1",
                         replace_config={"replacement": "***"})
        g = _create_group(client)
        s = _create_sample(client, text="V1 secret")
        _add_to_group(client, g["id"], r["id"])
        _run_group(client, s["id"], g["id"])

        client.put(f"/api/v1/rules/{r['id']}",
                   json={"match_value": "V2",
                         "replace_config": {"replacement": "###"}})
        _run_group(client, s["id"], g["id"])

        resp = client.get(f"/api/v1/audit/rules/{r['id']}")
        data = resp.json()
        assert len(data["config_versions"]) >= 1

    def test_rule_view_total_hits(self, client):
        r = _create_rule(client, match_value="HIT")
        g = _create_group(client)
        s = _create_sample(client, text="HIT HIT HIT")
        _add_to_group(client, g["id"], r["id"])
        _run_group(client, s["id"], g["id"])

        resp = client.get(f"/api/v1/audit/rules/{r['id']}")
        data = resp.json()
        assert data["total_hits"] >= 1
        assert data["last_hit_at"] is not None

    def test_rule_view_not_found(self, client):
        resp = client.get("/api/v1/audit/rules/9999")
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "NOT_FOUND"

    def test_rule_view_no_runs_returns_zero_hits(self, client):
        r = _create_rule(client)
        resp = client.get(f"/api/v1/audit/rules/{r['id']}")
        data = resp.json()
        assert data["total_hits"] == 0
        assert data["last_hit_at"] is None
        assert data["config_versions"] == []


class TestSampleAuditView:

    def test_sample_view_latest_run(self, client):
        r = _create_rule(client)
        g = _create_group(client)
        s = _create_sample(client)
        _add_to_group(client, g["id"], r["id"])
        run = _run_group(client, s["id"], g["id"])

        resp = client.get(f"/api/v1/audit/samples/{s['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sample_id"] == s["id"]
        assert data["latest_run"] is not None
        assert data["latest_run"]["id"] == run["id"]

    def test_sample_view_rule_hit_distribution(self, client):
        r1 = _create_rule(client, rule_name="r1", match_value="AAA",
                          replace_config={"replacement": "X"}, priority=10)
        r2 = _create_rule(client, rule_name="r2", match_value="BBB",
                          replace_config={"replacement": "Y"}, priority=20)
        g = _create_group(client)
        s = _create_sample(client, text="AAA BBB AAA")
        _add_to_group(client, g["id"], r1["id"])
        _add_to_group(client, g["id"], r2["id"])
        _run_group(client, s["id"], g["id"])

        resp = client.get(f"/api/v1/audit/samples/{s['id']}")
        data = resp.json()
        dist = data["rule_hit_distribution"]
        assert len(dist) >= 2
        rule_ids = [d["rule_id"] for d in dist]
        assert r1["id"] in rule_ids
        assert r2["id"] in rule_ids
        r1_stat = [d for d in dist if d["rule_id"] == r1["id"]][0]
        assert r1_stat["total_hits"] >= 2

    def test_sample_view_latest_regression(self, client):
        r = _create_rule(client)
        g = _create_group(client)
        s = _create_sample(client)
        _add_to_group(client, g["id"], r["id"])
        _run_group(client, s["id"], g["id"])

        client.post("/api/v1/regression/replay",
                    json={"sample_id": s["id"], "group_id": g["id"]})

        resp = client.get(f"/api/v1/audit/samples/{s['id']}")
        data = resp.json()
        assert data["latest_regression"] is not None
        assert data["latest_regression"]["is_consistent"] is True

    def test_sample_view_not_found(self, client):
        resp = client.get("/api/v1/audit/samples/9999")
        assert resp.status_code == 404

    def test_sample_view_no_runs(self, client):
        s = _create_sample(client)
        resp = client.get(f"/api/v1/audit/samples/{s['id']}")
        data = resp.json()
        assert data["latest_run"] is None
        assert data["latest_regression"] is None
        assert data["rule_hit_distribution"] == []


class TestGroupAuditView:

    def test_group_view_current_members(self, client):
        r1 = _create_rule(client, rule_name="r1")
        r2 = _create_rule(client, rule_name="r2", match_value="OTHER")
        g = _create_group(client)
        _add_to_group(client, g["id"], r1["id"])
        _add_to_group(client, g["id"], r2["id"])

        resp = client.get(f"/api/v1/audit/groups/{g['id']}")
        data = resp.json()
        assert set(data["current_members"]) == {r1["id"], r2["id"]}

    def test_group_view_historical_snapshots(self, client):
        r = _create_rule(client)
        g = _create_group(client)
        s = _create_sample(client)
        _add_to_group(client, g["id"], r["id"])
        _run_group(client, s["id"], g["id"])

        resp = client.get(f"/api/v1/audit/groups/{g['id']}")
        data = resp.json()
        assert len(data["historical_snapshots"]) >= 1
        assert data["historical_snapshots"][0]["rule_ids"] == [r["id"]]

    def test_group_view_member_change_diff_added(self, client):
        r1 = _create_rule(client, rule_name="r1", match_value="AAA")
        g = _create_group(client)
        s = _create_sample(client, text="AAA BBB")
        _add_to_group(client, g["id"], r1["id"])
        _run_group(client, s["id"], g["id"])

        r2 = _create_rule(client, rule_name="r2", match_value="BBB")
        _add_to_group(client, g["id"], r2["id"])

        resp = client.get(f"/api/v1/audit/groups/{g['id']}")
        data = resp.json()
        diff = data["member_change_diff"]
        assert diff is not None
        assert r2["id"] in diff["added"]
        assert "新增规则" in diff["execution_diff_summary"]

    def test_group_view_member_change_diff_removed(self, client):
        r1 = _create_rule(client, rule_name="r1", match_value="AAA")
        r2 = _create_rule(client, rule_name="r2", match_value="BBB")
        g = _create_group(client)
        s = _create_sample(client, text="AAA BBB")
        _add_to_group(client, g["id"], r1["id"])
        _add_to_group(client, g["id"], r2["id"])
        _run_group(client, s["id"], g["id"])

        client.delete(f"/api/v1/groups/{g['id']}/rules/{r2['id']}")

        resp = client.get(f"/api/v1/audit/groups/{g['id']}")
        data = resp.json()
        diff = data["member_change_diff"]
        assert diff is not None
        assert r2["id"] in diff["removed"]
        assert "移除规则" in diff["execution_diff_summary"]

    def test_group_view_no_changes(self, client):
        r = _create_rule(client)
        g = _create_group(client)
        s = _create_sample(client)
        _add_to_group(client, g["id"], r["id"])
        _run_group(client, s["id"], g["id"])

        resp = client.get(f"/api/v1/audit/groups/{g['id']}")
        data = resp.json()
        diff = data["member_change_diff"]
        assert diff is not None
        assert diff["added"] == []
        assert diff["removed"] == []

    def test_group_view_not_found(self, client):
        resp = client.get("/api/v1/audit/groups/9999")
        assert resp.status_code == 404


class TestAuditEventsList:

    def test_list_events_filter_by_type(self, client):
        _create_rule(client)
        resp = client.get("/api/v1/audit/events",
                          params={"event_type": "RULE_CREATE"})
        assert resp.status_code == 200
        for e in resp.json():
            assert e["event_type"] == "RULE_CREATE"

    def test_list_events_filter_by_target(self, client):
        r = _create_rule(client)
        resp = client.get("/api/v1/audit/events",
                          params={"target_type": "rule", "target_id": r["id"]})
        assert resp.status_code == 200
        for e in resp.json():
            assert e["target_id"] == r["id"]

    def test_list_events_limit(self, client):
        for i in range(5):
            _create_rule(client, rule_name=f"rule_{i}")
        resp = client.get("/api/v1/audit/events",
                          params={"event_type": "RULE_CREATE", "limit": 3})
        assert len(resp.json()) <= 3
