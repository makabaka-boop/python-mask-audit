from __future__ import annotations
"""规则冲突检测测试。"""
import pytest

from app.core.conflict import ConflictDetector


def _make_rule(rule_id, match_type="exact", match_value="test",
               field_type="text", strategy="fixed", config=None,
               priority=100, enabled=True):
    return {
        "id": rule_id,
        "rule_name": f"rule_{rule_id}",
        "field_type": field_type,
        "match_type": match_type,
        "match_value": match_value,
        "replace_strategy": strategy,
        "replace_config": config or {},
        "priority": priority,
        "enabled": enabled,
    }


class TestConflictDetectorUnit:

    def test_duplicate_exact_same_field_type(self):
        rules = [
            _make_rule(1, match_type="exact", match_value="SECRET", field_type="code"),
            _make_rule(2, match_type="exact", match_value="SECRET", field_type="code"),
        ]
        conflicts = ConflictDetector.detect(rules)
        dup = [c for c in conflicts if c["conflict_type"] == ConflictDetector.DUPLICATE_EXACT]
        assert len(dup) == 1
        assert set(dup[0]["rule_ids"]) == {1, 2}
        assert dup[0]["severity"] == "high"

    def test_duplicate_exact_different_field_type_no_conflict(self):
        rules = [
            _make_rule(1, match_type="exact", match_value="SECRET", field_type="code"),
            _make_rule(2, match_type="exact", match_value="SECRET", field_type="name"),
        ]
        conflicts = ConflictDetector.detect(rules)
        dup = [c for c in conflicts if c["conflict_type"] == ConflictDetector.DUPLICATE_EXACT]
        assert len(dup) == 0

    def test_three_duplicate_exact_rules(self):
        rules = [
            _make_rule(1, match_value="ABC", field_type="f1"),
            _make_rule(2, match_value="ABC", field_type="f1"),
            _make_rule(3, match_value="ABC", field_type="f1"),
        ]
        conflicts = ConflictDetector.detect(rules)
        dup = [c for c in conflicts if c["conflict_type"] == ConflictDetector.DUPLICATE_EXACT]
        assert len(dup) == 1
        assert set(dup[0]["rule_ids"]) == {1, 2, 3}

    def test_contains_overlap_one_contains_another(self):
        rules = [
            _make_rule(1, match_type="contains", match_value="123", field_type="phone"),
            _make_rule(2, match_type="contains", match_value="12", field_type="phone"),
        ]
        conflicts = ConflictDetector.detect(rules)
        overlap = [c for c in conflicts if c["conflict_type"] == ConflictDetector.CONTAINS_OVERLAP]
        assert len(overlap) == 1
        assert set(overlap[0]["rule_ids"]) == {1, 2}
        assert overlap[0]["severity"] == "medium"

    def test_contains_no_overlap_different_values(self):
        rules = [
            _make_rule(1, match_type="contains", match_value="abc", field_type="text"),
            _make_rule(2, match_type="contains", match_value="xyz", field_type="text"),
        ]
        conflicts = ConflictDetector.detect(rules)
        overlap = [c for c in conflicts if c["conflict_type"] == ConflictDetector.CONTAINS_OVERLAP]
        assert len(overlap) == 0

    def test_contains_overlap_different_field_type_no_conflict(self):
        rules = [
            _make_rule(1, match_type="contains", match_value="123", field_type="phone"),
            _make_rule(2, match_type="contains", match_value="12", field_type="id"),
        ]
        conflicts = ConflictDetector.detect(rules)
        overlap = [c for c in conflicts if c["conflict_type"] == ConflictDetector.CONTAINS_OVERLAP]
        assert len(overlap) == 0

    def test_exact_and_contains_overlap(self):
        rules = [
            _make_rule(1, match_type="exact", match_value="hello", field_type="text"),
            _make_rule(2, match_type="contains", match_value="ell", field_type="text"),
        ]
        conflicts = ConflictDetector.detect(rules)
        overlap = [c for c in conflicts if c["conflict_type"] == ConflictDetector.CONTAINS_OVERLAP]
        assert len(overlap) == 1

    def test_priority_conflict_different_strategy(self):
        rules = [
            _make_rule(1, match_value="a", strategy="fixed", config={"replacement": "***"}, priority=10, field_type="f1"),
            _make_rule(2, match_value="b", strategy="keep_edges", config={"left": 1}, priority=10, field_type="f2"),
        ]
        conflicts = ConflictDetector.detect(rules)
        pc = [c for c in conflicts if c["conflict_type"] == ConflictDetector.PRIORITY_CONFLICT]
        assert len(pc) == 1
        assert set(pc[0]["rule_ids"]) == {1, 2}
        assert pc[0]["severity"] == "medium"

    def test_priority_conflict_different_config(self):
        rules = [
            _make_rule(1, match_value="a", strategy="keep_edges",
                       config={"left": 1, "right": 1}, priority=10, field_type="f1"),
            _make_rule(2, match_value="b", strategy="keep_edges",
                       config={"left": 3, "right": 4}, priority=10, field_type="f2"),
        ]
        conflicts = ConflictDetector.detect(rules)
        pc = [c for c in conflicts if c["conflict_type"] == ConflictDetector.PRIORITY_CONFLICT]
        assert len(pc) == 1

    def test_same_priority_same_strategy_and_config_no_conflict(self):
        rules = [
            _make_rule(1, match_value="a", strategy="fixed", config={"replacement": "***"}, priority=10, field_type="f1"),
            _make_rule(2, match_value="b", strategy="fixed", config={"replacement": "***"}, priority=10, field_type="f2"),
        ]
        conflicts = ConflictDetector.detect(rules)
        pc = [c for c in conflicts if c["conflict_type"] == ConflictDetector.PRIORITY_CONFLICT]
        assert len(pc) == 0

    def test_different_priority_no_conflict(self):
        rules = [
            _make_rule(1, match_value="a", strategy="fixed", priority=10, field_type="f1"),
            _make_rule(2, match_value="b", strategy="keep_edges", priority=20, field_type="f2"),
        ]
        conflicts = ConflictDetector.detect(rules)
        pc = [c for c in conflicts if c["conflict_type"] == ConflictDetector.PRIORITY_CONFLICT]
        assert len(pc) == 0

    def test_disabled_rules_skipped(self):
        rules = [
            _make_rule(1, match_value="DUP", field_type="f1", enabled=False),
            _make_rule(2, match_value="DUP", field_type="f1", enabled=False),
        ]
        conflicts = ConflictDetector.detect(rules)
        assert len(conflicts) == 0

    def test_no_conflicts_clean_rules(self):
        rules = [
            _make_rule(1, match_type="exact", match_value="aaa", field_type="f1", priority=10),
            _make_rule(2, match_type="contains", match_value="bbb", field_type="f2", priority=20),
        ]
        conflicts = ConflictDetector.detect(rules)
        assert len(conflicts) == 0

    def test_config_as_json_string(self):
        rules = [
            _make_rule(1, match_value="a", strategy="fixed", config='{"replacement": "X"}', priority=10, field_type="f1"),
            _make_rule(2, match_value="b", strategy="fixed", config='{"replacement": "Y"}', priority=10, field_type="f2"),
        ]
        conflicts = ConflictDetector.detect(rules)
        pc = [c for c in conflicts if c["conflict_type"] == ConflictDetector.PRIORITY_CONFLICT]
        assert len(pc) == 1


class TestConflictAPI:

    def _create_rule(self, client, **overrides):
        payload = {
            "rule_name": "test_rule",
            "match_type": "exact",
            "match_value": "TEST",
            "replace_strategy": "fixed",
            "replace_config": {"replacement": "***"},
            "priority": 100,
            "field_type": "text",
        }
        payload.update(overrides)
        resp = client.post("/api/v1/rules", json=payload)
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_detect_conflicts_empty_group(self, client):
        group = client.post("/api/v1/groups", json={"group_name": "g1"}).json()
        resp = client.get(f"/api/v1/conflicts/groups/{group['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["conflicts"] == []

    def test_detect_duplicate_exact_via_api(self, client):
        r1 = self._create_rule(client, rule_name="r1", match_value="SECRET", field_type="code")
        r2 = self._create_rule(client, rule_name="r2", match_value="SECRET", field_type="code")
        group = client.post("/api/v1/groups", json={"group_name": "g1"}).json()
        client.post(f"/api/v1/groups/{group['id']}/rules",
                    json={"group_id": group["id"], "rule_id": r1["id"]})
        client.post(f"/api/v1/groups/{group['id']}/rules",
                    json={"group_id": group["id"], "rule_id": r2["id"]})

        resp = client.get(f"/api/v1/conflicts/groups/{group['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        types = [c["conflict_type"] for c in data["conflicts"]]
        assert "duplicate_exact" in types

    def test_detect_contains_overlap_via_api(self, client):
        r1 = self._create_rule(client, rule_name="r1", match_type="contains",
                               match_value="12345", field_type="phone")
        r2 = self._create_rule(client, rule_name="r2", match_type="contains",
                               match_value="123", field_type="phone")
        group = client.post("/api/v1/groups", json={"group_name": "g1"}).json()
        for rid in [r1["id"], r2["id"]]:
            client.post(f"/api/v1/groups/{group['id']}/rules",
                        json={"group_id": group["id"], "rule_id": rid})

        resp = client.get(f"/api/v1/conflicts/groups/{group['id']}")
        data = resp.json()
        types = [c["conflict_type"] for c in data["conflicts"]]
        assert "contains_overlap" in types

    def test_detect_priority_conflict_via_api(self, client):
        r1 = self._create_rule(client, rule_name="r1", match_value="aaa",
                               strategy="fixed", priority=10, field_type="f1")
        r2 = self._create_rule(client, rule_name="r2", match_value="bbb",
                               replace_strategy="keep_edges",
                               replace_config={"left": 1, "right": 1},
                               priority=10, field_type="f2")
        group = client.post("/api/v1/groups", json={"group_name": "g1"}).json()
        for rid in [r1["id"], r2["id"]]:
            client.post(f"/api/v1/groups/{group['id']}/rules",
                        json={"group_id": group["id"], "rule_id": rid})

        resp = client.get(f"/api/v1/conflicts/groups/{group['id']}")
        data = resp.json()
        types = [c["conflict_type"] for c in data["conflicts"]]
        assert "priority_conflict" in types

    def test_conflict_group_not_found(self, client):
        resp = client.get("/api/v1/conflicts/groups/9999")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error_code"] == "NOT_FOUND"

    def test_conflicts_do_not_block_execution(self, client):
        r1 = self._create_rule(client, rule_name="r1", match_value="DUP", field_type="f1")
        r2 = self._create_rule(client, rule_name="r2", match_value="DUP", field_type="f1")
        group = client.post("/api/v1/groups", json={"group_name": "g1"}).json()
        for rid in [r1["id"], r2["id"]]:
            client.post(f"/api/v1/groups/{group['id']}/rules",
                        json={"group_id": group["id"], "rule_id": rid})

        conflict_resp = client.get(f"/api/v1/conflicts/groups/{group['id']}")
        assert conflict_resp.json()["total"] >= 1

        sample = client.post("/api/v1/samples", json={
            "sample_name": "s1", "raw_text": "this has DUP in it"
        }).json()

        run_resp = client.post("/api/v1/runs/group", json={
            "sample_id": sample["id"], "group_id": group["id"]
        })
        assert run_resp.status_code == 201
        run_data = run_resp.json()
        assert "DUP" not in run_data["output_text"]

    def test_conflict_response_structure(self, client):
        r1 = self._create_rule(client, rule_name="r1", match_value="X", field_type="f1")
        r2 = self._create_rule(client, rule_name="r2", match_value="X", field_type="f1")
        group = client.post("/api/v1/groups", json={"group_name": "g1"}).json()
        for rid in [r1["id"], r2["id"]]:
            client.post(f"/api/v1/groups/{group['id']}/rules",
                        json={"group_id": group["id"], "rule_id": rid})

        resp = client.get(f"/api/v1/conflicts/groups/{group['id']}")
        data = resp.json()
        conflict = data["conflicts"][0]
        assert "rule_ids" in conflict
        assert "conflict_type" in conflict
        assert "message" in conflict
        assert "severity" in conflict
        assert isinstance(conflict["rule_ids"], list)
        assert conflict["severity"] in ("high", "medium", "low")
