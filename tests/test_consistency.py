from __future__ import annotations
"""一致性自检测试。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.consistency import ConsistencyChecker
from app.models import HitDetail, Rule, RunRecord, RuleSnapshot, SnapshotItem


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


def _create_sample(client, name="s1", text="hello SECRET"):
    return client.post("/api/v1/samples", json={
        "sample_name": name, "raw_text": text
    }).json()


def _setup_group_run(client):
    r = _create_rule(client)
    g = _create_group(client)
    s = _create_sample(client)
    client.post(f"/api/v1/groups/{g['id']}/rules",
                json={"group_id": g["id"], "rule_id": r["id"]})
    run = client.post("/api/v1/runs/group",
                      json={"sample_id": s["id"], "group_id": g["id"]}).json()
    return r, g, s, run


class TestConsistencyCheckPass:

    def test_all_checks_pass_on_clean_data(self, client):
        _setup_group_run(client)
        resp = client.get("/api/v1/consistency")
        assert resp.status_code == 200
        data = resp.json()
        assert data["all_passed"] is True
        assert data["total_issues"] == 0
        assert len(data["checks"]) == 7
        check_names = [c["check_name"] for c in data["checks"]]
        assert "orphan_hit_details" in check_names
        assert "group_run_missing_snapshot" in check_names
        assert "snapshot_hit_mismatch" in check_names
        assert "preview_data_leaked" in check_names
        assert "disabled_rule_in_run" in check_names
        assert "invalid_regex_residual" in check_names
        assert "regression_missing_baseline" in check_names
        for check in data["checks"]:
            assert check["passed"] is True
            assert check["issue_count"] == 0

    def test_check_structure(self, client):
        resp = client.get("/api/v1/consistency")
        data = resp.json()
        for check in data["checks"]:
            assert "check_name" in check
            assert "passed" in check
            assert "issue_count" in check
            assert "details" in check
            assert isinstance(check["details"], list)

    def test_self_check_writes_audit_event(self, client):
        client.get("/api/v1/consistency")
        events = client.get("/api/v1/audit/events",
                            params={"event_type": "CONSISTENCY_CHECK"}).json()
        assert len(events) >= 1


class TestConsistencyCheckAnomalies:

    def test_orphan_hit_details_detected(self, client, db_engine):
        r, g, s, run = _setup_group_run(client)

        Session = sessionmaker(bind=db_engine)
        db = Session()
        try:
            orphan = HitDetail(
                run_id=99999, rule_id=r["id"],
                matched_count=1, before_fragment="x", after_fragment="*",
            )
            db.add(orphan)
            db.commit()
        finally:
            db.close()

        resp = client.get("/api/v1/consistency")
        data = resp.json()
        check = [c for c in data["checks"]
                 if c["check_name"] == "orphan_hit_details"][0]
        assert check["passed"] is False
        assert check["issue_count"] >= 1
        assert any(d["run_id"] == 99999 for d in check["details"])

    def test_group_run_missing_snapshot_detected(self, client, db_engine):
        r = _create_rule(client)
        g = _create_group(client)
        s = _create_sample(client)
        client.post(f"/api/v1/groups/{g['id']}/rules",
                    json={"group_id": g["id"], "rule_id": r["id"]})
        client.post("/api/v1/runs/group",
                    json={"sample_id": s["id"], "group_id": g["id"]})

        Session = sessionmaker(bind=db_engine)
        db = Session()
        try:
            db.query(RunRecord).filter(
                RunRecord.group_id == g["id"]
            ).update({RunRecord.snapshot_id: None})
            db.commit()
        finally:
            db.close()

        resp = client.get("/api/v1/consistency")
        data = resp.json()
        check = [c for c in data["checks"]
                 if c["check_name"] == "group_run_missing_snapshot"][0]
        assert check["passed"] is False
        assert check["issue_count"] >= 1

    def test_invalid_regex_residual_detected(self, client, db_engine):
        Session = sessionmaker(bind=db_engine)
        db = Session()
        try:
            bad_rule = Rule(
                rule_name="bad_regex", field_type="text",
                match_type="regex", match_value="[invalid",
                replace_strategy="fixed", replace_config="{}",
                priority=100, enabled=True,
            )
            db.add(bad_rule)
            db.commit()
        finally:
            db.close()

        resp = client.get("/api/v1/consistency")
        data = resp.json()
        check = [c for c in data["checks"]
                 if c["check_name"] == "invalid_regex_residual"][0]
        assert check["passed"] is False
        assert check["issue_count"] >= 1
        assert any("正则" in d["reason"] for d in check["details"])

    def test_regression_missing_baseline_detected(self, client, db_engine):
        r = _create_rule(client)
        g = _create_group(client)
        s = _create_sample(client)
        client.post(f"/api/v1/groups/{g['id']}/rules",
                    json={"group_id": g["id"], "rule_id": r["id"]})
        client.post("/api/v1/runs/group",
                    json={"sample_id": s["id"], "group_id": g["id"]})

        Session = sessionmaker(bind=db_engine)
        db = Session()
        try:
            db.query(RuleSnapshot).filter(
                RuleSnapshot.group_id == g["id"]
            ).delete()
            db.commit()
        finally:
            db.close()

        resp = client.get("/api/v1/consistency")
        data = resp.json()
        check = [c for c in data["checks"]
                 if c["check_name"] == "regression_missing_baseline"][0]
        assert check["passed"] is False
        assert check["issue_count"] >= 1
        assert any(d["group_id"] == g["id"] for d in check["details"])

    def test_preview_data_leaked_detects_zero_count_hit_detail(self, client, db_engine):
        r, g, s, run = _setup_group_run(client)

        Session = sessionmaker(bind=db_engine)
        db = Session()
        try:
            bad_detail = HitDetail(
                run_id=run["id"], rule_id=r["id"],
                matched_count=0, before_fragment="", after_fragment="",
            )
            db.add(bad_detail)
            db.commit()
        finally:
            db.close()

        resp = client.get("/api/v1/consistency")
        data = resp.json()
        check = [c for c in data["checks"]
                 if c["check_name"] == "preview_data_leaked"][0]
        assert check["passed"] is False

    def test_disabled_rule_in_run_detected(self, client, db_engine):
        r, g, s, run = _setup_group_run(client)
        client.patch(f"/api/v1/rules/{r['id']}/enabled", json={"enabled": False})

        resp = client.get("/api/v1/consistency")
        data = resp.json()
        check = [c for c in data["checks"]
                 if c["check_name"] == "disabled_rule_in_run"][0]
        assert check["passed"] is False
        assert check["issue_count"] >= 1

    def test_snapshot_hit_mismatch_detected(self, client, db_engine):
        r, g, s, run = _setup_group_run(client)

        Session = sessionmaker(bind=db_engine)
        db = Session()
        try:
            other_rule = Rule(
                rule_name="other", field_type="text",
                match_type="exact", match_value="OTHER",
                replace_strategy="fixed", replace_config="{}",
                priority=200, enabled=True,
            )
            db.add(other_rule)
            db.commit()
            db.refresh(other_rule)

            mismatched = HitDetail(
                run_id=run["id"], rule_id=other_rule.id,
                matched_count=1, before_fragment="OTHER",
                after_fragment="***",
            )
            db.add(mismatched)
            db.commit()
        finally:
            db.close()

        resp = client.get("/api/v1/consistency")
        data = resp.json()
        check = [c for c in data["checks"]
                 if c["check_name"] == "snapshot_hit_mismatch"][0]
        assert check["passed"] is False


class TestSeedData:

    def test_seed_data_usable(self, db_engine, tmp_path):
        import importlib
        import sys

        seed_db = str(tmp_path / "seed_test.db")

        from app import database as db_module
        original_url = db_module.DATABASE_URL
        original_engine = db_module.engine

        seed_engine = create_engine(
            f"sqlite:///{seed_db}",
            connect_args={"check_same_thread": False},
        )
        db_module.engine = seed_engine
        db_module.SessionLocal.configure(bind=seed_engine)

        try:
            from app.database import Base
            Base.metadata.create_all(bind=seed_engine)

            from scripts.seed_data import seed
            seed()

            Session = sessionmaker(bind=seed_engine)
            session = Session()
            try:
                rules = session.query(Rule).all()
                assert len(rules) == 4

                runs = session.query(RunRecord).all()
                assert len(runs) == 1
                assert runs[0].snapshot_id is not None
                assert runs[0].hit_count >= 1

                snapshots = session.query(RuleSnapshot).all()
                assert len(snapshots) == 1

                items = session.query(SnapshotItem).all()
                assert len(items) == 4

                hit_details = session.query(HitDetail).all()
                assert len(hit_details) >= 1
            finally:
                session.close()
        finally:
            db_module.engine = original_engine
            db_module.SessionLocal.configure(bind=original_engine)
            seed_engine.dispose()


class TestApiV1Prefix:

    def test_all_new_endpoints_use_v1_prefix(self, client):
        r = _create_rule(client)
        g = _create_group(client)
        s = _create_sample(client)
        client.post(f"/api/v1/groups/{g['id']}/rules",
                    json={"group_id": g["id"], "rule_id": r["id"]})

        endpoints = [
            ("GET", "/api/v1/consistency", None),
            ("GET", "/api/v1/audit/events", None),
            ("GET", f"/api/v1/audit/rules/{r['id']}", None),
            ("GET", f"/api/v1/audit/samples/{s['id']}", None),
            ("GET", f"/api/v1/audit/groups/{g['id']}", None),
            ("GET", f"/api/v1/conflicts/groups/{g['id']}", None),
            ("POST", "/api/v1/regression/replay",
             {"sample_id": s["id"], "group_id": g["id"]}),
        ]
        for method, path, body in endpoints:
            if method == "GET":
                resp = client.get(path)
            else:
                resp = client.post(path, json=body)
            assert resp.status_code != 404, f"{method} {path} returned 404"

    def test_consistency_without_prefix_returns_404(self, client):
        resp = client.get("/consistency")
        assert resp.status_code == 404

    def test_audit_without_prefix_returns_404(self, client):
        resp = client.get("/audit/events")
        assert resp.status_code == 404
