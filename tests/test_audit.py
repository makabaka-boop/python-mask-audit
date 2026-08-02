"""审计查询模块集成测试：三个维度聚合 + 审计事件写入 + 预览不落库。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.helpers import make_env, ServerFixture


class AuditTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = make_env()
        cls.srv = ServerFixture()

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()
        try:
            os.remove(cls.db_path)
        except OSError:
            pass

    def _rule(self, **kw):
        payload = {
            "rule_name": "phone",
            "field_type": "phone",
            "match_type": "regex",
            "match_value": r"\d{11}",
            "replace_strategy": "keep_edges",
            "replace_config": {"left": 3, "right": 4, "mask_char": "*"},
            "priority": 100,
        }
        payload.update(kw)
        _, body = self.srv.request("POST", "/api/v1/rules", payload)
        return body

    def _events_of(self, event_type):
        _, body = self.srv.request("GET", "/api/v1/audit/events")
        return [e for e in body["items"] if e["event_type"] == event_type]


class TestRuleDimension(AuditTestCase):
    def test_rule_aggregation(self):
        r = self._rule(rule_name="rule_dim")
        rid = r["id"]
        _, s = self.srv.request("POST", "/api/v1/samples",
                                {"sample_name": "sd", "raw_text": "num 13800001111"})
        # 两次单条执行，产生命中
        self.srv.request("POST", "/api/v1/runs/rule", {"rule_id": rid, "sample_id": s["id"]})
        self.srv.request("POST", "/api/v1/runs/rule", {"rule_id": rid, "sample_id": s["id"]})
        # 改优先级 → 历史快照出现新版本
        self.srv.request("POST", f"/api/v1/rules/{rid}/priority", {"priority": 5})
        self.srv.request("POST", "/api/v1/runs/rule", {"rule_id": rid, "sample_id": s["id"]})

        status, body = self.srv.request("GET", f"/api/v1/audit/rules/{rid}")
        self.assertEqual(status, 200)
        self.assertEqual(body["dimension"], "rule")
        self.assertEqual(body["current_config"]["id"], rid)
        self.assertEqual(body["total_matched"], 3)
        self.assertEqual(body["hit_records"], 3)
        self.assertIsNotNone(body["last_hit_at"])
        # 历史版本中应包含优先级 100 与 5 两个版本
        priorities = {v["priority"] for v in body["history_versions"]}
        self.assertIn(100, priorities)
        self.assertIn(5, priorities)

    def test_rule_not_found(self):
        status, body = self.srv.request("GET", "/api/v1/audit/rules/999999")
        self.assertEqual(status, 404)
        self.assertEqual(body["error_code"], "not_found")


class TestSampleDimension(AuditTestCase):
    def test_sample_aggregation(self):
        r = self._rule(rule_name="sample_dim")
        _, s = self.srv.request("POST", "/api/v1/samples",
                                {"sample_name": "sample_agg", "raw_text": "call 13800001111"})
        sid = s["id"]
        _, g = self.srv.request("POST", "/api/v1/groups", {"group_name": "sg"})
        gid = g["id"]
        self.srv.request("POST", f"/api/v1/groups/{gid}/members", {"rule_id": r["id"]})
        self.srv.request("POST", "/api/v1/runs/group", {"group_id": gid, "sample_id": sid})
        # 回归验证 → 产生 latest_regression
        self.srv.request("POST", "/api/v1/regression", {"sample_id": sid})

        status, body = self.srv.request("GET", f"/api/v1/audit/samples/{sid}")
        self.assertEqual(status, 200)
        self.assertEqual(body["dimension"], "sample")
        self.assertIsNotNone(body["latest_run"])
        self.assertEqual(body["latest_run"]["sample_id"], sid)
        self.assertIsNotNone(body["latest_regression"])
        # 命中分布包含该规则
        rule_ids = {d["rule_id"] for d in body["rule_hit_distribution"]}
        self.assertIn(r["id"], rule_ids)


class TestGroupDimension(AuditTestCase):
    def test_group_member_change_summary(self):
        r1 = self._rule(rule_name="g_r1", match_value=r"\d{11}")
        r2 = self._rule(rule_name="g_r2", match_type="contains", match_value="secret",
                        replace_strategy="fixed", replace_config={"value": "X"})
        _, s = self.srv.request("POST", "/api/v1/samples",
                                {"sample_name": "gs", "raw_text": "call 13800001111 secret"})
        sid = s["id"]
        _, g = self.srv.request("POST", "/api/v1/groups", {"group_name": "gg"})
        gid = g["id"]
        # 第一次演练：只有 r1
        self.srv.request("POST", f"/api/v1/groups/{gid}/members", {"rule_id": r1["id"]})
        self.srv.request("POST", "/api/v1/runs/group", {"group_id": gid, "sample_id": sid})
        # 加入 r2 后再演练：成员变化
        self.srv.request("POST", f"/api/v1/groups/{gid}/members", {"rule_id": r2["id"]})
        self.srv.request("POST", "/api/v1/runs/group", {"group_id": gid, "sample_id": sid})

        status, body = self.srv.request("GET", f"/api/v1/audit/groups/{gid}")
        self.assertEqual(status, 200)
        self.assertEqual(body["dimension"], "group")
        current_ids = {m["id"] for m in body["current_members"]}
        self.assertEqual(current_ids, {r1["id"], r2["id"]})
        history_ids = {m["rule_id"] for m in body["history_members"]}
        self.assertTrue({r1["id"], r2["id"]}.issubset(history_ids))
        # 成员变化摘要中应能看到 r2 在两次演练之间被加入
        transitions = body["member_change_summary"]["run_transitions"]
        self.assertTrue(len(transitions) >= 1)
        added_all = set()
        for t in transitions:
            added_all.update(t["added_rule_ids"])
        self.assertIn(r2["id"], added_all)


class TestAuditEventsWritten(AuditTestCase):
    def test_events_written_for_all_actions(self):
        r = self._rule(rule_name="evt")
        rid = r["id"]
        _, s = self.srv.request("POST", "/api/v1/samples",
                                {"sample_name": "evt_s", "raw_text": "x 13800001111"})
        _, g = self.srv.request("POST", "/api/v1/groups", {"group_name": "evt_g"})
        gid = g["id"]

        self.srv.request("POST", f"/api/v1/groups/{gid}/members", {"rule_id": rid})
        self.srv.request("POST", f"/api/v1/rules/{rid}/disable")
        self.srv.request("POST", f"/api/v1/rules/{rid}/enable")
        self.srv.request("POST", f"/api/v1/rules/{rid}/priority", {"priority": 3})
        self.srv.request("POST", "/api/v1/runs/rule", {"rule_id": rid, "sample_id": s["id"]})
        self.srv.request("POST", "/api/v1/runs/group", {"group_id": gid, "sample_id": s["id"]})
        self.srv.request("POST", "/api/v1/preview", {"rule_id": rid, "input_text": "13800001111"})
        self.srv.request("POST", "/api/v1/regression", {"sample_id": s["id"]})
        self.srv.request("DELETE", f"/api/v1/groups/{gid}/members/{rid}")

        _, body = self.srv.request("GET", "/api/v1/audit/events")
        types = {e["event_type"] for e in body["items"]}
        for expected in [
            "group_member_added", "rule_disabled", "rule_enabled",
            "rule_priority_changed", "run_executed", "preview",
            "regression", "group_member_removed",
        ]:
            self.assertIn(expected, types, f"缺少审计事件 {expected}")


class TestPreviewNoRecordAgain(AuditTestCase):
    def test_preview_writes_audit_but_no_run(self):
        r = self._rule(rule_name="prev_evt")
        _, before_runs = self.srv.request("GET", "/api/v1/runs")
        prev_events = len(self._events_of("preview"))

        status, prev = self.srv.request("POST", "/api/v1/preview",
                                        {"rule_id": r["id"], "input_text": "13800001111"})
        self.assertEqual(status, 200)

        _, after_runs = self.srv.request("GET", "/api/v1/runs")
        # 预览不写入演练记录
        self.assertEqual(len(before_runs["items"]), len(after_runs["items"]))
        # 但写入了 preview 审计事件
        self.assertEqual(len(self._events_of("preview")), prev_events + 1)
        # 也不产生命中明细：命中分布查询该规则应仍为空
        _, dist = self.srv.request("GET", f"/api/v1/audit/rules/{r['id']}")
        self.assertEqual(dist["hit_records"], 0)


if __name__ == "__main__":
    unittest.main()
