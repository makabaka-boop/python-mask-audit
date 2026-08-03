import json
import os
import subprocess
import sys

import pytest

from app import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    app.testing = True
    with app.test_client() as c:
        yield c


def make_rule(client, **overrides):
    payload = {
        "rule_name": "手机号规则",
        "field_type": "phone",
        "match_type": "regex",
        "match_value": r"1\d{10}",
        "replace_strategy": "middle_mask",
        "replace_config": {"mask_char": "*"},
        "priority": 10,
    }
    payload.update(overrides)
    return client.post("/api/v1/rules", json=payload)


# ---------- 健康检查 ----------

def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


# ---------- 规则校验 ----------

def test_create_rule_ok(client):
    resp = make_rule(client)
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["rule_name"] == "手机号规则"
    assert body["enabled"] is True
    assert body["created_at"] and body["updated_at"]


def test_create_rule_invalid_match_type(client):
    resp = make_rule(client, match_type="fuzzy")
    assert resp.status_code == 400
    assert resp.get_json()["error_code"] == "VALIDATION_ERROR"


def test_create_rule_invalid_strategy(client):
    resp = make_rule(client, replace_strategy="hash")
    assert resp.status_code == 400


def test_create_rule_empty_match_value(client):
    resp = make_rule(client, match_value="  ")
    assert resp.status_code == 400
    assert "match_value" in resp.get_json()["message"]


def test_create_rule_invalid_regex(client):
    resp = make_rule(client, match_value="([abc")
    assert resp.status_code == 400
    assert "regex_error" in resp.get_json()["details"]


def test_create_rule_duplicate_name(client):
    assert make_rule(client).status_code == 201
    resp = make_rule(client)
    assert resp.status_code == 409
    assert resp.get_json()["error_code"] == "CONFLICT"


def test_error_response_shape(client):
    resp = client.get("/api/v1/rules/999")
    body = resp.get_json()
    assert resp.status_code == 404
    assert set(body.keys()) == {"error_code", "message", "details"}


# ---------- 启停与优先级 ----------

def test_toggle_and_priority(client):
    rule_id = make_rule(client).get_json()["id"]
    resp = client.patch(f"/api/v1/rules/{rule_id}/status", json={"enabled": False})
    assert resp.get_json()["enabled"] is False

    resp = client.post(f"/api/v1/rules/{rule_id}/execute",
                       json={"input_text": "电话13812345678"})
    assert resp.status_code == 400  # 禁用规则不能演练

    resp = client.patch(f"/api/v1/rules/{rule_id}/priority", json={"priority": 99})
    assert resp.get_json()["priority"] == 99


# ---------- 分组与演练 ----------

def _build_group(client):
    r1 = make_rule(client).get_json()
    r2 = make_rule(client, rule_name="身份证规则", field_type="id_card",
                   match_value=r"\d{17}[\dXx]", priority=5).get_json()
    group = client.post("/api/v1/groups", json={
        "group_name": "身份类", "description": "身份信息脱敏"}).get_json()
    client.post(f"/api/v1/groups/{group['id']}/rules", json={"rule_id": r1["id"]})
    client.post(f"/api/v1/groups/{group['id']}/rules", json={"rule_id": r2["id"]})
    return group, r1, r2


def test_group_add_remove_and_conflict(client):
    group, r1, _ = _build_group(client)
    resp = client.post(f"/api/v1/groups/{group['id']}/rules", json={"rule_id": r1["id"]})
    assert resp.status_code == 409  # 重复添加

    resp = client.delete(f"/api/v1/groups/{group['id']}/rules/{r1['id']}")
    assert resp.get_json()["removed"] is True
    resp = client.delete(f"/api/v1/groups/{group['id']}/rules/{r1['id']}")
    assert resp.status_code == 404


def test_group_execute_skips_disabled_and_saves_snapshot(client):
    group, r1, r2 = _build_group(client)
    client.patch(f"/api/v1/rules/{r2['id']}/status", json={"enabled": False})
    sample = client.post("/api/v1/samples", json={
        "sample_name": "样例A", "sample_category": "客服",
        "raw_text": "手机13812345678，证件110101199001011234",
        "expected_note": "证件号规则已禁用"}).get_json()

    resp = client.post(f"/api/v1/groups/{group['id']}/execute",
                       json={"sample_id": sample["id"]})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["executed_rule_ids"] == [r1["id"]]  # 禁用规则不参与
    assert "手机1*********8" in body["output_text"]

    run = client.get(f"/api/v1/runs/{body['run_id']}").get_json()
    assert run["hit_count"] == body["hit_count"] == 2  # 手机号正则也命中身份证号前缀
    assert run["hit_details"][0]["rule_id"] == r1["id"]

    snapshot = client.get(f"/api/v1/runs/{body['run_id']}/snapshot").get_json()
    snap = snapshot["rule_snapshots"][0]
    assert snap["rule_id"] == r1["id"]
    assert snap["replace_strategy"] == "middle_mask"
    assert snap["enabled"] == 1 and snap["priority"] == 10


def test_execute_is_idempotent(client):
    rule_id = make_rule(client).get_json()["id"]
    text = "联系13812345678或13998765432"
    first = client.post(f"/api/v1/rules/{rule_id}/execute",
                        json={"input_text": text}).get_json()
    second = client.post(f"/api/v1/rules/{rule_id}/execute",
                         json={"input_text": first["output_text"]}).get_json()
    assert first["hit_count"] == 2
    assert second["hit_count"] == 0  # 重复执行不再增加星号
    assert second["output_text"] == first["output_text"]


def test_priority_order_affects_output(client):
    text = "abc"
    r1 = make_rule(client, rule_name="r1", match_type="exact", match_value="abc",
                   replace_strategy="fixed", replace_config={"replacement": "xyz"},
                   priority=1).get_json()
    r2 = make_rule(client, rule_name="r2", match_type="exact", match_value="xyz",
                   replace_strategy="fixed", replace_config={"replacement": "***"},
                   priority=9).get_json()
    group = client.post("/api/v1/groups", json={"group_name": "顺序组"}).get_json()
    client.post(f"/api/v1/groups/{group['id']}/rules", json={"rule_id": r1["id"]})
    client.post(f"/api/v1/groups/{group['id']}/rules", json={"rule_id": r2["id"]})
    resp = client.post(f"/api/v1/groups/{group['id']}/execute",
                       json={"input_text": text})
    # r2 先执行（不命中 abc），r1 后执行把 abc 换成 xyz
    assert resp.get_json()["output_text"] == "xyz"


# ---------- 替换策略 ----------

def test_keep_edges_short_text(client):
    rule_id = make_rule(client, rule_name="姓名规则", field_type="name",
                        match_type="exact", match_value="李雷",
                        replace_strategy="keep_edges",
                        replace_config={"left": 3, "right": 3, "mask_char": "#"}).get_json()["id"]
    resp = client.post(f"/api/v1/rules/{rule_id}/execute", json={"input_text": "我是李雷"})
    assert resp.get_json()["output_text"] == "我是李#"  # 短文本至少保留首字符


def test_middle_mask_short_text_not_fully_masked(client):
    for text in ["韩", "韩梅"]:
        rule_id = make_rule(client, rule_name=f"短文本-{text}", field_type="name",
                            match_type="exact", match_value=text,
                            replace_strategy="middle_mask").get_json()["id"]
        resp = client.post(f"/api/v1/rules/{rule_id}/execute",
                           json={"input_text": text})
        output = resp.get_json()["output_text"]
        assert output.startswith("韩")  # 不能全部替换掉


# ---------- 预览 / 统计 / 回归 ----------

def test_preview_does_not_persist(client):
    rule_id = make_rule(client).get_json()["id"]
    resp = client.post("/api/v1/preview", json={
        "input_text": "电话13812345678", "rule_ids": [rule_id]})
    body = resp.get_json()
    assert "1*********8" in body["output_text"]
    assert body["hit_details"][0]["matched_count"] == 1

    stats = client.get(f"/api/v1/rules/{rule_id}/stats").get_json()
    assert stats["run_count"] == 0 and stats["total_hits"] == 0  # 未写入演练记录


def test_stats_accumulate(client):
    rule_id = make_rule(client).get_json()["id"]
    client.post(f"/api/v1/rules/{rule_id}/execute", json={"input_text": "13812345678"})
    client.post(f"/api/v1/rules/{rule_id}/execute",
                json={"input_text": "13812345678和13998765432"})
    stats = client.get(f"/api/v1/rules/{rule_id}/stats").get_json()
    assert stats["run_count"] == 2
    assert stats["total_hits"] == 3


def test_regression_pass_and_detect_change(client):
    group, r1, _ = _build_group(client)
    client.post(f"/api/v1/groups/{group['id']}/execute",
                json={"input_text": "手机13812345678"})

    resp = client.post("/api/v1/regression", json={"group_id": group["id"]})
    assert resp.get_json()["passed"] is True
    assert resp.get_json()["rule_changes"] == []

    client.patch(f"/api/v1/rules/{r1['id']}/priority", json={"priority": 77})
    resp = client.post("/api/v1/regression", json={"group_id": group["id"]})
    body = resp.get_json()
    assert body["passed"] is False
    change = body["rule_changes"][0]
    assert change["change_type"] == "modified"
    assert change["field_changes"]["priority"] == {"before": 10, "after": 77}
    assert body["rerun_output_text"] == body["previous_output_text"]  # 结果未变


def test_regression_detects_rule_removed_from_group(client):
    group, r1, _ = _build_group(client)
    client.post(f"/api/v1/groups/{group['id']}/execute",
                json={"input_text": "手机13812345678"})
    client.delete(f"/api/v1/groups/{group['id']}/rules/{r1['id']}")
    resp = client.post("/api/v1/regression", json={"group_id": group["id"]})
    body = resp.get_json()
    assert body["passed"] is False
    assert body["output_changed"] is True


def test_audit_events_recorded(client):
    make_rule(client)
    resp = client.get("/api/v1/audits")
    events = resp.get_json()["audits"]
    assert any(e["event_type"] == "create_rule" for e in events)


# ---------- 规则冲突检测 ----------

def _build_conflict_group(client):
    """构造同时包含三类冲突的分组。"""
    r1 = make_rule(client, rule_name="姓名A", field_type="name", match_type="exact",
                   match_value="张三", replace_strategy="fixed",
                   replace_config={"replacement": "***"}, priority=1).get_json()
    r2 = make_rule(client, rule_name="姓名B", field_type="name", match_type="exact",
                   match_value="张三", replace_strategy="middle_mask",
                   priority=2).get_json()
    r3 = make_rule(client, rule_name="地址长", field_type="addr", match_type="contains",
                   match_value="北京市海淀区", priority=5).get_json()
    r4 = make_rule(client, rule_name="地址短", field_type="addr", match_type="contains",
                   match_value="北京市", priority=6).get_json()
    r5 = make_rule(client, rule_name="同优先级1", field_type="phone", match_type="exact",
                   match_value="139", replace_strategy="fixed",
                   replace_config={"replacement": "AAA"}, priority=8).get_json()
    r6 = make_rule(client, rule_name="同优先级2", field_type="phone", match_type="exact",
                   match_value="138", replace_strategy="keep_edges",
                   replace_config={"left": 2, "right": 1}, priority=8).get_json()
    group = client.post("/api/v1/groups", json={"group_name": "冲突组"}).get_json()
    for r in (r1, r2, r3, r4, r5, r6):
        client.post(f"/api/v1/groups/{group['id']}/rules", json={"rule_id": r["id"]})
    return group, (r1, r2, r3, r4, r5, r6)


def test_conflicts_detects_three_types(client):
    group, (r1, r2, r3, r4, r5, r6) = _build_conflict_group(client)
    resp = client.get(f"/api/v1/groups/{group['id']}/conflicts")
    body = resp.get_json()
    assert resp.status_code == 200
    by_type = {c["conflict_type"]: c for c in body["conflicts"]}
    assert set(by_type) == {"duplicate_exact", "contains_overlap",
                            "same_priority_different_replace"}

    dup = by_type["duplicate_exact"]
    assert dup["rule_ids"] == sorted([r1["id"], r2["id"]])
    assert dup["severity"] == "high" and dup["message"]

    overlap = by_type["contains_overlap"]
    assert overlap["rule_ids"] == sorted([r3["id"], r4["id"]])
    assert overlap["severity"] == "medium"

    same_prio = by_type["same_priority_different_replace"]
    assert same_prio["rule_ids"] == sorted([r5["id"], r6["id"]])
    assert same_prio["severity"] == "low"


def test_conflicts_no_false_positive(client):
    group, _, _ = _build_group(client)
    body = client.get(f"/api/v1/groups/{group['id']}/conflicts").get_json()
    assert body["conflict_count"] == 0
    assert body["conflicts"] == []


def test_conflicts_do_not_block_execution(client):
    group, _ = _build_conflict_group(client)
    # 存在 high 级冲突，但保存、加组、执行均不被阻止
    resp = client.post(f"/api/v1/groups/{group['id']}/execute",
                       json={"input_text": "张三住在北京市海淀区"})
    assert resp.status_code == 200
    assert resp.get_json()["hit_count"] > 0


# ---------- 回归验证增强 ----------

def test_regression_by_sample_and_consistent(client):
    group, r1, _ = _build_group(client)
    sample = client.post("/api/v1/samples", json={
        "sample_name": "回归样例", "raw_text": "手机13812345678"}).get_json()
    client.post(f"/api/v1/groups/{group['id']}/execute",
                json={"sample_id": sample["id"]})

    # 只传 sample_id，自动定位最近一次使用的分组
    resp = client.post("/api/v1/regression", json={"sample_id": sample["id"]})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["group_id"] == group["id"]
    assert body["passed"] is True
    assert body["diff_sources"] == []
    assert body["output_changed"] is False


def test_regression_explains_replace_config_change(client):
    group, r1, _ = _build_group(client)
    sample = client.post("/api/v1/samples", json={
        "sample_name": "样例X", "raw_text": "手机13812345678"}).get_json()
    run = client.post(f"/api/v1/groups/{group['id']}/execute",
                      json={"sample_id": sample["id"]}).get_json()

    # 直接改库模拟规则配置变更（替换配置 left/right）
    db = client.application.extensions["db"]
    db.execute("UPDATE rules SET replace_config = ? WHERE id = ?",
               ('{"mask_char": "#"}', r1["id"]))

    resp = client.post("/api/v1/regression", json={"sample_id": sample["id"]})
    body = resp.get_json()
    assert body["passed"] is False
    sources = {s["source"] for s in body["diff_sources"]}
    assert sources == {"replace_config_change"}
    assert body["diff_sources"][0]["rule_ids"] == [r1["id"]]
    assert body["output_changed"] is True
    assert body["rerun_output_text"] != body["previous_output_text"]
    # 快照字段级差异说明
    change = next(c for c in body["rule_changes"] if c["rule_id"] == r1["id"])
    assert "replace_config" in change["field_changes"]


def test_regression_explains_rule_config_change(client):
    group, r1, _ = _build_group(client)
    client.post(f"/api/v1/groups/{group['id']}/execute",
                json={"input_text": "手机13812345678"})

    db = client.application.extensions["db"]
    db.execute("UPDATE rules SET match_value = ? WHERE id = ?", (r"1\d{9}", r1["id"]))

    body = client.post("/api/v1/regression", json={"group_id": group["id"]}).get_json()
    assert body["passed"] is False
    sources = {s["source"] for s in body["diff_sources"]}
    assert "rule_config_change" in sources


def test_regression_explains_member_and_priority_change(client):
    group, r1, r2 = _build_group(client)
    client.post(f"/api/v1/groups/{group['id']}/execute",
                json={"input_text": "手机13812345678，证件110101199001011234"})

    client.delete(f"/api/v1/groups/{group['id']}/rules/{r2['id']}")  # 成员变化
    client.patch(f"/api/v1/rules/{r1['id']}/priority", json={"priority": 55})  # 优先级变化

    body = client.post("/api/v1/regression", json={"group_id": group["id"]}).get_json()
    assert body["passed"] is False
    sources = {s["source"] for s in body["diff_sources"]}
    assert sources == {"member_change", "priority_change"}
    member = next(s for s in body["diff_sources"] if s["source"] == "member_change")
    assert member["rule_ids"] == [r2["id"]]
    assert member["message"]
    # 基于快照对比，而不是只比较文本
    assert body["rule_changes"] != []
    assert r2["id"] in body["snapshot_rule_ids"]


# ---------- 审计查询（三维度） ----------

def test_preview_writes_audit_but_not_run_records(client):
    rule_id = make_rule(client).get_json()["id"]
    client.post("/api/v1/preview", json={
        "input_text": "电话13812345678", "rule_ids": [rule_id]})

    events = client.get("/api/v1/audits").get_json()["audits"]
    preview_events = [e for e in events if e["event_type"] == "preview"]
    assert len(preview_events) == 1
    assert preview_events[0]["detail"]["rule_ids"] == [rule_id]

    # 预览仍不写演练记录和命中明细
    stats = client.get(f"/api/v1/rules/{rule_id}/stats").get_json()
    assert stats["run_count"] == 0 and stats["total_hits"] == 0


def test_audit_events_cover_all_actions(client):
    group, r1, _ = _build_group(client)
    client.patch(f"/api/v1/rules/{r1['id']}/status", json={"enabled": False})
    client.patch(f"/api/v1/rules/{r1['id']}/priority", json={"priority": 66})
    client.delete(f"/api/v1/groups/{group['id']}/rules/{r1['id']}")
    client.post(f"/api/v1/groups/{group['id']}/execute",
                json={"input_text": "手机13812345678"})
    client.post("/api/v1/preview", json={
        "input_text": "手机13812345678", "group_id": group["id"]})
    client.post("/api/v1/regression", json={"group_id": group["id"]})

    types = {e["event_type"] for e in client.get("/api/v1/audits").get_json()["audits"]}
    assert {"create_rule", "toggle_rule", "change_priority",
            "group_add_rule", "group_remove_rule", "execute_run",
            "preview", "regression_check"} <= types


def test_audit_rule_dimension(client):
    rule = make_rule(client).get_json()
    client.post(f"/api/v1/rules/{rule['id']}/execute",
                json={"input_text": "电话13812345678"})
    # 变更配置后再次演练，产生第二个快照版本
    db = client.application.extensions["db"]
    db.execute("UPDATE rules SET replace_config = ? WHERE id = ?",
               ('{"mask_char": "#"}', rule["id"]))
    client.post(f"/api/v1/rules/{rule['id']}/execute",
                json={"input_text": "电话13912345678"})

    body = client.get(f"/api/v1/audit/rules/{rule['id']}").get_json()
    assert body["current_config"]["replace_config"] == {"mask_char": "#"}
    assert len(body["config_versions"]) == 2
    assert body["config_versions"][0]["replace_config"] == {"mask_char": "*"}
    assert body["config_versions"][1]["replace_config"] == {"mask_char": "#"}
    assert body["config_versions"][0]["run_count"] == 1
    assert body["total_hits"] == 2
    assert body["last_hit_at"] is not None


def test_audit_rule_dimension_no_history(client):
    rule = make_rule(client).get_json()
    body = client.get(f"/api/v1/audit/rules/{rule['id']}").get_json()
    assert body["config_versions"] == []
    assert body["total_hits"] == 0
    assert body["last_hit_at"] is None


def test_audit_sample_dimension(client):
    group, r1, r2 = _build_group(client)
    sample = client.post("/api/v1/samples", json={
        "sample_name": "审计样例", "raw_text": "手机13812345678"}).get_json()
    client.post(f"/api/v1/groups/{group['id']}/execute",
                json={"sample_id": sample["id"]})
    client.post(f"/api/v1/rules/{r1['id']}/execute",
                json={"sample_id": sample["id"]})
    client.post("/api/v1/regression", json={"sample_id": sample["id"]})

    body = client.get(f"/api/v1/audit/samples/{sample['id']}").get_json()
    assert len(body["recent_runs"]) == 2
    assert body["recent_runs"][0]["run_id"] > body["recent_runs"][1]["run_id"]  # 倒序

    regression = body["latest_regression"]
    assert regression is not None
    assert regression["passed"] is True
    assert regression["group_id"] == group["id"]

    dist = {d["rule_id"]: d for d in body["rule_hit_distribution"]}
    assert dist[r1["id"]]["total_hits"] == 2  # 分组演练 1 次 + 单规则演练 1 次
    assert dist[r1["id"]]["run_count"] == 2
    assert dist[r1["id"]]["rule_name"] == "手机号规则"


def test_audit_group_dimension_member_change_summary(client):
    r1 = make_rule(client, rule_name="姓名", field_type="name", match_type="exact",
                   match_value="张三", replace_strategy="fixed",
                   replace_config={"replacement": "<姓名>"}, priority=9).get_json()
    r2 = make_rule(client, rule_name="城市", field_type="addr", match_type="exact",
                   match_value="北京市", replace_strategy="fixed",
                   replace_config={"replacement": "<城市>"}, priority=8).get_json()
    group = client.post("/api/v1/groups", json={"group_name": "摘要组"}).get_json()
    client.post(f"/api/v1/groups/{group['id']}/rules", json={"rule_id": r1["id"]})
    client.post(f"/api/v1/groups/{group['id']}/rules", json={"rule_id": r2["id"]})

    text = "张三在北京市"
    client.post(f"/api/v1/groups/{group['id']}/execute", json={"input_text": text})
    client.delete(f"/api/v1/groups/{group['id']}/rules/{r2['id']}")  # 成员变化
    client.post(f"/api/v1/groups/{group['id']}/execute", json={"input_text": text})

    body = client.get(f"/api/v1/audit/groups/{group['id']}").get_json()
    assert [m["id"] for m in body["current_members"]] == [r1["id"]]
    snapshot_ids = {m["rule_id"] for m in body["snapshot_members"]}
    assert snapshot_ids == {r1["id"], r2["id"]}
    r2_snap = next(m for m in body["snapshot_members"] if m["rule_id"] == r2["id"])
    assert r2_snap["run_count"] == 1

    summary = body["member_change_summary"]
    assert summary["removed_rule_ids"] == [r2["id"]]
    assert summary["added_rule_ids"] == []
    assert summary["same_input"] is True
    assert summary["previous_hit_count"] == 2
    assert summary["latest_hit_count"] == 1
    assert summary["output_changed"] is True
    assert "北京市" in summary["latest_output_text"]  # 移除后不再脱敏


def test_audit_group_dimension_no_runs(client):
    group = client.post("/api/v1/groups", json={"group_name": "空组"}).get_json()
    body = client.get(f"/api/v1/audit/groups/{group['id']}").get_json()
    assert body["current_members"] == []
    assert body["snapshot_members"] == []
    assert body["member_change_summary"] is None


# ---------- 一致性自检 ----------

SELF_CHECK_NAMES = {
    "orphan_hit_details", "group_run_missing_snapshot", "snapshot_hit_mismatch",
    "preview_residue_in_runs", "disabled_rule_participation",
    "invalid_regex_residue", "regression_missing_baseline",
}


def test_selfcheck_passes_on_healthy_chain(client):
    group, r1, _ = _build_group(client)
    sample = client.post("/api/v1/samples", json={
        "sample_name": "自检样例", "raw_text": "手机13812345678"}).get_json()
    client.post(f"/api/v1/groups/{group['id']}/execute",
                json={"sample_id": sample["id"]})
    client.post("/api/v1/preview", json={
        "input_text": "手机13812345678", "group_id": group["id"]})
    client.post("/api/v1/regression", json={"sample_id": sample["id"]})

    resp = client.get("/api/v1/selfcheck")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["passed"] is True
    assert body["check_count"] == 7 and body["failed_count"] == 0
    assert {c["check_name"] for c in body["checks"]} == SELF_CHECK_NAMES
    for c in body["checks"]:
        assert c["passed"] is True
        assert c["issue_count"] == 0 and c["details"] == []


def test_selfcheck_detects_anomalies(client):
    db = client.application.extensions["db"]
    db.execute("PRAGMA foreign_keys = OFF")
    now = "2026-01-01T00:00:00"

    # 1. 孤立命中明细（run 和 rule 都不存在）
    db.execute("INSERT INTO hit_details (run_id, rule_id, matched_count, "
               "before_fragment, after_fragment) VALUES (999, 999, 1, 'a', 'b')")
    # 2. 缺失快照的分组演练
    db.execute("INSERT INTO drill_runs (sample_id, rule_id, group_id, input_text, "
               "output_text, hit_count, executed_at) VALUES (NULL, NULL, 888, 'x', 'y', 0, ?)",
               (now,))
    # 3. 预览数据误落库（rule_id 和 group_id 都为空）
    db.execute("INSERT INTO drill_runs (sample_id, rule_id, group_id, input_text, "
               "output_text, hit_count, executed_at) "
               "VALUES (NULL, NULL, NULL, 'x', 'y', 0, ?)", (now,))
    # 4. 非法正则残留（绕过 API 校验直接写库）
    db.execute("INSERT INTO rules (rule_name, field_type, match_type, match_value, "
               "replace_strategy, replace_config, priority, enabled, created_at, updated_at) "
               "VALUES ('坏正则', 'phone', 'regex', '([abc', 'fixed', '{}', 0, 1, ?, ?)",
               (now, now))
    # 5. 禁用规则参与演练（快照 enabled=0 却有命中）
    rule = make_rule(client, rule_name="被禁用规则").get_json()
    run_id = db.execute(
        "INSERT INTO drill_runs (sample_id, rule_id, group_id, input_text, output_text, "
        "hit_count, executed_at) VALUES (NULL, ?, NULL, 'x', 'y', 1, ?)",
        (rule["id"], now)).lastrowid
    db.execute("INSERT INTO rule_snapshots (run_id, rule_id, rule_name, enabled, priority, "
               "match_type, match_value, replace_strategy, replace_config) "
               "VALUES (?, ?, '被禁用规则', 0, 10, 'regex', '1\\d{10}', 'middle_mask', '{}')",
               (run_id, rule["id"]))
    db.execute("INSERT INTO hit_details (run_id, rule_id, matched_count, before_fragment, "
               "after_fragment) VALUES (?, ?, 1, 'a', 'b')", (run_id, rule["id"]))
    # 6. 回归验证缺少历史基准（基准 run 不存在）
    db.execute("INSERT INTO audit_events (event_type, entity_type, entity_id, detail, "
               "created_at) VALUES ('regression_check', 'run', 9999, '{}', ?)", (now,))

    body = client.get("/api/v1/selfcheck").get_json()
    assert body["passed"] is False
    by_name = {c["check_name"]: c for c in body["checks"]}

    orphan = by_name["orphan_hit_details"]
    assert orphan["issue_count"] >= 1
    assert any(d["run_id"] == 999 for d in orphan["details"])

    missing = by_name["group_run_missing_snapshot"]
    assert any(d["group_id"] == 888 for d in missing["details"])

    mismatch = by_name["snapshot_hit_mismatch"]
    assert mismatch["issue_count"] >= 1  # run 999 的命中无快照对应

    residue = by_name["preview_residue_in_runs"]
    assert residue["issue_count"] == 1

    disabled = by_name["disabled_rule_participation"]
    assert disabled["issue_count"] == 1
    assert disabled["details"][0]["rule_id"] == rule["id"]

    regex = by_name["invalid_regex_residue"]
    assert regex["issue_count"] == 1
    assert regex["details"][0]["rule_name"] == "坏正则"
    assert "regex_error" in regex["details"][0]

    baseline = by_name["regression_missing_baseline"]
    assert baseline["issue_count"] == 1
    assert baseline["details"][0]["base_run_id"] == 9999


# ---------- 初始化样例数据脚本 ----------

def test_seed_script_creates_usable_data(tmp_path):
    db_path = str(tmp_path / "seed.db")
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "scripts", "seed.py")

    result = subprocess.run([sys.executable, script, db_path],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["hit_count"] >= 1
    assert "138****5678" in summary["output_text"]

    # 重复执行安全：复用同名规则与分组
    result2 = subprocess.run([sys.executable, script, db_path],
                             capture_output=True, text=True)
    assert result2.returncode == 0, result2.stderr

    # 初始化的数据可以继续走完整链路
    app = create_app(db_path)
    c = app.test_client()
    assert len(c.get("/api/v1/rules").get_json()["rules"]) == 3
    resp = c.post(f"/api/v1/groups/{summary['group_id']}/execute",
                  json={"sample_id": summary["sample_id"]})
    assert resp.status_code == 200
    assert c.get("/api/v1/selfcheck").get_json()["passed"] is True


# ---------- 路由前缀 ----------

def test_all_routes_keep_api_v1_prefix(client):
    routes = [r.rule for r in client.application.url_map.iter_rules()
              if r.endpoint != "static"]
    assert routes, "应至少注册一些路由"
    assert all(r.startswith("/api/v1") for r in routes)
    assert client.get("/api/v1/selfcheck").status_code == 200
    assert client.get("/selfcheck").status_code == 404
