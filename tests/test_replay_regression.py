from __future__ import annotations
"""回放回归验证测试。"""
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


def _setup_group_with_run(client, rule_overrides=None, sample_text="hello SECRET world"):
    rule = _create_rule(client, **(rule_overrides or {}))
    group = client.post("/api/v1/groups", json={"group_name": "g1"}).json()
    client.post(f"/api/v1/groups/{group['id']}/rules",
                json={"group_id": group["id"], "rule_id": rule["id"]})
    sample = client.post("/api/v1/samples", json={
        "sample_name": "s1", "raw_text": sample_text
    }).json()
    run = client.post("/api/v1/runs/group", json={
        "sample_id": sample["id"], "group_id": group["id"]
    }).json()
    return rule, group, sample, run


class TestReplayRegressionConsistent:

    def test_replay_consistent_no_changes(self, client):
        rule, group, sample, run = _setup_group_with_run(client)

        resp = client.post("/api/v1/regression/replay", json={
            "sample_id": sample["id"], "group_id": group["id"]
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["is_consistent"] is True
        assert data["historical_output"] == data["current_output"]
        assert data["snapshot_id"] == run["snapshot_id"]
        assert data["run_id"] == run["id"]
        assert data["rules_changed"] == []
        assert data["rules_added"] == []
        assert data["rules_removed"] == []

    def test_replay_response_contains_required_fields(self, client):
        rule, group, sample, run = _setup_group_with_run(client)

        resp = client.post("/api/v1/regression/replay", json={
            "sample_id": sample["id"], "group_id": group["id"]
        })
        data = resp.json()
        assert "historical_output" in data
        assert "current_output" in data
        assert "is_consistent" in data
        assert "diff_reasons" in data
        assert "rules_changed" in data
        assert "rules_added" in data
        assert "rules_removed" in data
        assert "rules_unchanged" in data
        assert "snapshot_id" in data
        assert "run_id" in data


class TestReplayRegressionInconsistent:

    def test_replay_inconsistent_after_replace_config_change(self, client):
        rule, group, sample, run = _setup_group_with_run(client, {
            "replace_strategy": "fixed",
            "replace_config": {"replacement": "***"},
        })

        client.put(f"/api/v1/rules/{rule['id']}", json={
            "replace_config": {"replacement": "###"}
        })

        resp = client.post("/api/v1/regression/replay", json={
            "sample_id": sample["id"], "group_id": group["id"]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_consistent"] is False
        assert data["historical_output"] != data["current_output"]
        assert len(data["rules_changed"]) >= 1
        changed_rule = data["rules_changed"][0]
        assert changed_rule["rule_id"] == rule["id"]
        assert "replace_config" in changed_rule["diff_fields"]
        assert any("替换配置" in r for r in data["diff_reasons"])

    def test_replay_inconsistent_after_match_value_change(self, client):
        rule, group, sample, run = _setup_group_with_run(client, {
            "match_value": "SECRET",
        })

        client.put(f"/api/v1/rules/{rule['id']}", json={
            "match_value": "SECRET_NEW"
        })

        resp = client.post("/api/v1/regression/replay", json={
            "sample_id": sample["id"], "group_id": group["id"]
        })
        data = resp.json()
        assert data["is_consistent"] is False
        changed = data["rules_changed"][0]
        assert "match_value" in changed["diff_fields"]
        assert any("规则配置" in r for r in data["diff_reasons"])

    def test_replay_inconsistent_after_priority_change(self, client):
        rule1 = _create_rule(client, rule_name="r1", match_value="AAA",
                             replace_strategy="fixed",
                             replace_config={"replacement": "X"},
                             priority=10, field_type="f1")
        rule2 = _create_rule(client, rule_name="r2", match_value="BBB",
                             replace_strategy="fixed",
                             replace_config={"replacement": "Y"},
                             priority=20, field_type="f1")
        group = client.post("/api/v1/groups", json={"group_name": "g1"}).json()
        for rid in [rule1["id"], rule2["id"]]:
            client.post(f"/api/v1/groups/{group['id']}/rules",
                        json={"group_id": group["id"], "rule_id": rid})
        sample = client.post("/api/v1/samples", json={
            "sample_name": "s1", "raw_text": "AAA and BBB"
        }).json()
        client.post("/api/v1/runs/group", json={
            "sample_id": sample["id"], "group_id": group["id"]
        })

        client.patch(f"/api/v1/rules/{rule1['id']}/priority", json={"priority": 30})

        resp = client.post("/api/v1/regression/replay", json={
            "sample_id": sample["id"], "group_id": group["id"]
        })
        data = resp.json()
        changed_ids = [c["rule_id"] for c in data["rules_changed"]]
        assert rule1["id"] in changed_ids
        rule1_change = [c for c in data["rules_changed"] if c["rule_id"] == rule1["id"]][0]
        assert "priority" in rule1_change["diff_fields"]
        assert any("优先级" in r for r in data["diff_reasons"])

    def test_replay_inconsistent_after_rule_removed_from_group(self, client):
        rule, group, sample, run = _setup_group_with_run(client)

        client.delete(f"/api/v1/groups/{group['id']}/rules/{rule['id']}")

        resp = client.post("/api/v1/regression/replay", json={
            "sample_id": sample["id"], "group_id": group["id"]
        })
        data = resp.json()
        assert data["is_consistent"] is False
        assert rule["id"] in data["rules_removed"]
        assert any("移除规则" in r for r in data["diff_reasons"])

    def test_replay_inconsistent_after_rule_disabled(self, client):
        rule, group, sample, run = _setup_group_with_run(client)

        client.patch(f"/api/v1/rules/{rule['id']}/enabled", json={"enabled": False})

        resp = client.post("/api/v1/regression/replay", json={
            "sample_id": sample["id"], "group_id": group["id"]
        })
        data = resp.json()
        assert data["is_consistent"] is False
        changed_ids = [c["rule_id"] for c in data["rules_changed"]]
        assert rule["id"] in changed_ids
        rule_change = [c for c in data["rules_changed"] if c["rule_id"] == rule["id"]][0]
        assert "enabled" in rule_change["diff_fields"]
        assert any("启用状态" in r for r in data["diff_reasons"])

    def test_replay_consistent_with_no_effect_change(self, client):
        rule, group, sample, run = _setup_group_with_run(
            client,
            sample_text="this has NO_MATCH here",
            rule_overrides={"match_value": "SECRET"},
        )

        client.put(f"/api/v1/rules/{rule['id']}", json={
            "replace_config": {"replacement": "###"}
        })

        resp = client.post("/api/v1/regression/replay", json={
            "sample_id": sample["id"], "group_id": group["id"]
        })
        data = resp.json()
        assert data["is_consistent"] is True
        assert data["historical_output"] == data["current_output"]
        assert len(data["rules_changed"]) >= 1
        assert any("未影响此样例" in r for r in data["diff_reasons"])


class TestReplayRegressionErrors:

    def test_replay_group_not_found(self, client):
        resp = client.post("/api/v1/regression/replay", json={
            "sample_id": 1, "group_id": 9999
        })
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "NOT_FOUND"

    def test_replay_sample_not_found(self, client):
        group = client.post("/api/v1/groups", json={"group_name": "g1"}).json()
        resp = client.post("/api/v1/regression/replay", json={
            "sample_id": 9999, "group_id": group["id"]
        })
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "NOT_FOUND"

    def test_replay_no_historical_run(self, client):
        rule = _create_rule(client)
        group = client.post("/api/v1/groups", json={"group_name": "g1"}).json()
        client.post(f"/api/v1/groups/{group['id']}/rules",
                    json={"group_id": group["id"], "rule_id": rule["id"]})
        sample = client.post("/api/v1/samples", json={
            "sample_name": "s1", "raw_text": "test"
        }).json()

        resp = client.post("/api/v1/regression/replay", json={
            "sample_id": sample["id"], "group_id": group["id"]
        })
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "VALIDATION_ERROR"

    def test_replay_uses_snapshot_not_just_text(self, client):
        rule, group, sample, run = _setup_group_with_run(client)

        snapshot_resp = client.get(f"/api/v1/snapshots/{run['snapshot_id']}")
        assert snapshot_resp.status_code == 200
        snapshot_data = snapshot_resp.json()
        assert len(snapshot_data["items"]) == 1
        assert snapshot_data["items"][0]["rule_id"] == rule["id"]
        assert snapshot_data["items"][0]["match_value"] == "SECRET"

        resp = client.post("/api/v1/regression/replay", json={
            "sample_id": sample["id"], "group_id": group["id"]
        })
        data = resp.json()
        assert data["snapshot_id"] == run["snapshot_id"]
        assert data["rules_unchanged"] == [rule["id"]]
