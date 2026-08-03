"""HTTP API 集成测试。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.helpers import make_env, ServerFixture


class ApiTestCase(unittest.TestCase):
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

    # -- 便捷方法 -- #
    def create_rule(self, **kw):
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
        return self.srv.request("POST", "/api/v1/rules", payload)


class TestHealth(ApiTestCase):
    def test_health(self):
        status, body = self.srv.request("GET", "/api/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")


class TestRuleCrud(ApiTestCase):
    def test_create_and_get(self):
        status, body = self.create_rule(rule_name="r1")
        self.assertEqual(status, 201)
        self.assertEqual(body["rule_name"], "r1")
        rid = body["id"]
        status, got = self.srv.request("GET", f"/api/v1/rules/{rid}")
        self.assertEqual(status, 200)
        self.assertEqual(got["id"], rid)

    def test_empty_match_value_rejected(self):
        status, body = self.create_rule(match_value="")
        self.assertEqual(status, 400)
        self.assertEqual(body["error_code"], "validation_error")

    def test_bad_match_type(self):
        status, body = self.create_rule(match_type="fuzzy")
        self.assertEqual(status, 400)

    def test_bad_regex(self):
        status, body = self.create_rule(match_type="regex", match_value="([a-z")
        self.assertEqual(status, 400)
        self.assertEqual(body["error_code"], "validation_error")

    def test_bad_strategy(self):
        status, body = self.create_rule(replace_strategy="scramble")
        self.assertEqual(status, 400)

    def test_enable_disable(self):
        _, body = self.create_rule(rule_name="toggle")
        rid = body["id"]
        status, d = self.srv.request("POST", f"/api/v1/rules/{rid}/disable")
        self.assertEqual(status, 200)
        self.assertFalse(d["enabled"])
        status, e = self.srv.request("POST", f"/api/v1/rules/{rid}/enable")
        self.assertTrue(e["enabled"])

    def test_priority(self):
        _, body = self.create_rule(rule_name="prio")
        rid = body["id"]
        status, d = self.srv.request("POST", f"/api/v1/rules/{rid}/priority", {"priority": 5})
        self.assertEqual(status, 200)
        self.assertEqual(d["priority"], 5)


class TestGroupAndRun(ApiTestCase):
    def test_group_flow(self):
        _, r1 = self.create_rule(rule_name="g_phone", match_value=r"\d{11}")
        _, g = self.srv.request("POST", "/api/v1/groups", {"group_name": "pii"})
        gid = g["id"]
        status, members = self.srv.request("POST", f"/api/v1/groups/{gid}/members", {"rule_id": r1["id"]})
        self.assertEqual(status, 201)
        self.assertEqual(len(members["items"]), 1)

        # 运行分组演练
        status, run = self.srv.request(
            "POST", "/api/v1/runs/group", {"group_id": gid, "input_text": "call 13800001111 now"}
        )
        self.assertEqual(status, 201)
        self.assertEqual(run["output_text"], "call 138****1111 now")
        self.assertEqual(run["hit_count"], 1)
        self.assertTrue(len(run["rule_snapshots"]) >= 1)

        # 明细
        status, detail = self.srv.request("GET", f"/api/v1/runs/{run['id']}")
        self.assertEqual(status, 200)
        self.assertTrue(len(detail["hit_details"]) >= 1)

    def test_disabled_rule_excluded_from_group(self):
        _, r = self.create_rule(rule_name="dis", match_value="topsecret", match_type="contains",
                                replace_strategy="fixed", replace_config={"value": "X"})
        _, g = self.srv.request("POST", "/api/v1/groups", {"group_name": "grp_dis"})
        gid = g["id"]
        self.srv.request("POST", f"/api/v1/groups/{gid}/members", {"rule_id": r["id"]})
        self.srv.request("POST", f"/api/v1/rules/{r['id']}/disable")
        _, run = self.srv.request("POST", "/api/v1/runs/group",
                                  {"group_id": gid, "input_text": "topsecret data"})
        # 禁用规则不参与演练
        self.assertEqual(run["output_text"], "topsecret data")
        self.assertEqual(run["hit_count"], 0)

    def test_remove_member(self):
        _, r = self.create_rule(rule_name="rm")
        _, g = self.srv.request("POST", "/api/v1/groups", {"group_name": "grp_rm"})
        gid = g["id"]
        self.srv.request("POST", f"/api/v1/groups/{gid}/members", {"rule_id": r["id"]})
        status, members = self.srv.request("DELETE", f"/api/v1/groups/{gid}/members/{r['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(len(members["items"]), 0)


class TestSingleRunAndDisabled(ApiTestCase):
    def test_run_single(self):
        _, r = self.create_rule(rule_name="single", match_value=r"\d{11}")
        status, run = self.srv.request("POST", "/api/v1/runs/rule",
                                       {"rule_id": r["id"], "input_text": "num 13800001111"})
        self.assertEqual(status, 201)
        self.assertEqual(run["output_text"], "num 138****1111")

    def test_run_disabled_rejected(self):
        _, r = self.create_rule(rule_name="single_dis")
        self.srv.request("POST", f"/api/v1/rules/{r['id']}/disable")
        status, body = self.srv.request("POST", "/api/v1/runs/rule",
                                        {"rule_id": r["id"], "input_text": "x"})
        self.assertEqual(status, 400)


class TestPreviewNoRecord(ApiTestCase):
    def test_preview_does_not_write_run(self):
        _, r = self.create_rule(rule_name="prev", match_value=r"\d{11}")
        _, before = self.srv.request("GET", "/api/v1/runs")
        status, prev = self.srv.request("POST", "/api/v1/preview",
                                        {"rule_id": r["id"], "input_text": "p 13800001111"})
        self.assertEqual(status, 200)
        self.assertEqual(prev["output_text"], "p 138****1111")
        self.assertIn("hit_details", prev)
        _, after = self.srv.request("GET", "/api/v1/runs")
        self.assertEqual(len(before["items"]), len(after["items"]))


class TestStatsAndRegression(ApiTestCase):
    def test_stats(self):
        _, r = self.create_rule(rule_name="stat", match_value=r"\d{11}")
        self.srv.request("POST", "/api/v1/runs/rule", {"rule_id": r["id"], "input_text": "13800001111"})
        self.srv.request("POST", "/api/v1/runs/rule", {"rule_id": r["id"], "input_text": "13800001111"})
        status, stats = self.srv.request("GET", f"/api/v1/rules/{r['id']}/stats")
        self.assertEqual(status, 200)
        self.assertEqual(stats["total_matched"], 2)
        self.assertEqual(stats["hit_records"], 2)

    def test_regression_detects_change(self):
        _, sample = self.srv.request("POST", "/api/v1/samples",
                                     {"sample_name": "s1", "raw_text": "phone 13800001111"})
        _, r = self.create_rule(rule_name="reg", match_value=r"\d{11}")
        _, g = self.srv.request("POST", "/api/v1/groups", {"group_name": "grp_reg"})
        gid = g["id"]
        self.srv.request("POST", f"/api/v1/groups/{gid}/members", {"rule_id": r["id"]})
        self.srv.request("POST", "/api/v1/runs/group", {"group_id": gid, "sample_id": sample["id"]})

        # 修改规则优先级后回归，应为不一致并归因 priority_change
        self.srv.request("POST", f"/api/v1/rules/{r['id']}/priority", {"priority": 1})
        status, reg = self.srv.request("POST", "/api/v1/regression", {"sample_id": sample["id"]})
        self.assertEqual(status, 200)
        self.assertFalse(reg["consistent"])
        self.assertEqual(reg["group_id"], gid)
        types = {d["difference_type"] for d in reg["differences"]}
        self.assertIn("priority_change", types)

    def test_regression_consistent(self):
        _, sample = self.srv.request("POST", "/api/v1/samples",
                                     {"sample_name": "s_consistent", "raw_text": "phone 13800001111"})
        _, r = self.create_rule(rule_name="reg_ok", match_value=r"\d{11}")
        _, g = self.srv.request("POST", "/api/v1/groups", {"group_name": "grp_reg_ok"})
        gid = g["id"]
        self.srv.request("POST", f"/api/v1/groups/{gid}/members", {"rule_id": r["id"]})
        self.srv.request("POST", "/api/v1/runs/group", {"group_id": gid, "sample_id": sample["id"]})

        # 不改任何东西，回归应一致，无差异
        status, reg = self.srv.request("POST", "/api/v1/regression", {"sample_id": sample["id"]})
        self.assertEqual(status, 200)
        self.assertTrue(reg["consistent"])
        self.assertTrue(reg["output_consistent"])
        self.assertEqual(reg["differences"], [])

    def test_regression_replace_config_change(self):
        _, sample = self.srv.request("POST", "/api/v1/samples",
                                     {"sample_name": "s_rc", "raw_text": "phone 13800001111"})
        _, r = self.create_rule(rule_name="reg_rc", match_value=r"\d{11}")
        _, g = self.srv.request("POST", "/api/v1/groups", {"group_name": "grp_rc"})
        gid = g["id"]
        self.srv.request("POST", f"/api/v1/groups/{gid}/members", {"rule_id": r["id"]})
        self.srv.request("POST", "/api/v1/runs/group", {"group_id": gid, "sample_id": sample["id"]})

        # 通过新建同名规则替换配置不方便，改优先级不覆盖 replace，这里删除旧成员换新配置规则
        _, r2 = self.create_rule(rule_name="reg_rc2", match_value=r"\d{11}",
                                 replace_strategy="fixed", replace_config={"value": "[PHONE]"})
        self.srv.request("DELETE", f"/api/v1/groups/{gid}/members/{r['id']}")
        self.srv.request("POST", f"/api/v1/groups/{gid}/members", {"rule_id": r2["id"]})
        status, reg = self.srv.request("POST", "/api/v1/regression", {"sample_id": sample["id"]})
        self.assertEqual(status, 200)
        self.assertFalse(reg["consistent"])
        types = {d["difference_type"] for d in reg["differences"]}
        # 成员发生了增删
        self.assertIn("member_change", types)

    def test_regression_no_history(self):
        _, sample = self.srv.request("POST", "/api/v1/samples",
                                     {"sample_name": "s_none", "raw_text": "abc"})
        status, body = self.srv.request("POST", "/api/v1/regression", {"sample_id": sample["id"]})
        self.assertEqual(status, 404)


class TestConflictDetection(ApiTestCase):
    def _group_with_rules(self, name, rules):
        _, g = self.srv.request("POST", "/api/v1/groups", {"group_name": name})
        gid = g["id"]
        ids = []
        for kw in rules:
            _, r = self.create_rule(**kw)
            ids.append(r["id"])
            self.srv.request("POST", f"/api/v1/groups/{gid}/members", {"rule_id": r["id"]})
        return gid, ids

    def test_duplicate_exact(self):
        gid, ids = self._group_with_rules("cf_dup", [
            {"rule_name": "e1", "field_type": "id_card", "match_type": "exact",
             "match_value": "110101", "replace_strategy": "fixed", "replace_config": {"value": "X"}},
            {"rule_name": "e2", "field_type": "id_card", "match_type": "exact",
             "match_value": "110101", "replace_strategy": "fixed", "replace_config": {"value": "X"}},
        ])
        status, body = self.srv.request("GET", f"/api/v1/groups/{gid}/conflicts")
        self.assertEqual(status, 200)
        types = {c["conflict_type"] for c in body["items"]}
        self.assertIn("duplicate_exact", types)
        for c in body["items"]:
            if c["conflict_type"] == "duplicate_exact":
                self.assertEqual(sorted(c["rule_ids"]), sorted(ids))
                self.assertIn("severity", c)
                self.assertIn("message", c)

    def test_contains_overlap(self):
        gid, ids = self._group_with_rules("cf_contains", [
            {"rule_name": "c1", "field_type": "text", "match_type": "contains",
             "match_value": "secret", "replace_strategy": "fixed", "replace_config": {"value": "X"}},
            {"rule_name": "c2", "field_type": "text", "match_type": "contains",
             "match_value": "top secret data", "replace_strategy": "fixed", "replace_config": {"value": "Y"}},
        ])
        status, body = self.srv.request("GET", f"/api/v1/groups/{gid}/conflicts")
        types = {c["conflict_type"] for c in body["items"]}
        self.assertIn("contains_overlap", types)

    def test_same_priority_different_replace(self):
        gid, ids = self._group_with_rules("cf_prio", [
            {"rule_name": "p1", "field_type": "text", "match_type": "contains",
             "match_value": "aaa", "replace_strategy": "fixed", "replace_config": {"value": "X"},
             "priority": 50},
            {"rule_name": "p2", "field_type": "text", "match_type": "contains",
             "match_value": "bbb", "replace_strategy": "keep_edges",
             "replace_config": {"left": 1, "right": 1}, "priority": 50},
        ])
        status, body = self.srv.request("GET", f"/api/v1/groups/{gid}/conflicts")
        types = {c["conflict_type"] for c in body["items"]}
        self.assertIn("same_priority_different_replace", types)

    def test_conflict_does_not_block_execution(self):
        # 存在冲突时，加入分组和执行演练均不受阻。
        gid, ids = self._group_with_rules("cf_nonblock", [
            {"rule_name": "n1", "field_type": "id", "match_type": "exact",
             "match_value": "dup", "replace_strategy": "fixed", "replace_config": {"value": "X"}},
            {"rule_name": "n2", "field_type": "id", "match_type": "exact",
             "match_value": "dup", "replace_strategy": "fixed", "replace_config": {"value": "X"}},
        ])
        # 确认有冲突
        _, body = self.srv.request("GET", f"/api/v1/groups/{gid}/conflicts")
        self.assertTrue(len(body["items"]) >= 1)
        # 仍可执行演练
        status, run = self.srv.request("POST", "/api/v1/runs/group",
                                       {"group_id": gid, "input_text": "dup"})
        self.assertEqual(status, 201)

    def test_no_conflict_clean_group(self):
        gid, ids = self._group_with_rules("cf_clean", [
            {"rule_name": "ok1", "field_type": "phone", "match_type": "regex",
             "match_value": r"\d{11}", "replace_strategy": "fixed",
             "replace_config": {"value": "P"}, "priority": 10},
            {"rule_name": "ok2", "field_type": "email", "match_type": "contains",
             "match_value": "@corp.com", "replace_strategy": "fixed",
             "replace_config": {"value": "E"}, "priority": 20},
        ])
        status, body = self.srv.request("GET", f"/api/v1/groups/{gid}/conflicts")
        self.assertEqual(status, 200)
        self.assertEqual(body["items"], [])


class TestErrors(ApiTestCase):
    def test_not_found(self):
        status, body = self.srv.request("GET", "/api/v1/rules/999999")
        self.assertEqual(status, 404)
        self.assertEqual(body["error_code"], "not_found")

    def test_route_not_found(self):
        status, body = self.srv.request("GET", "/api/v1/unknown")
        self.assertEqual(status, 404)
        self.assertEqual(body["error_code"], "route_not_found")

    def test_error_shape(self):
        status, body = self.create_rule(match_value="")
        self.assertIn("error_code", body)
        self.assertIn("message", body)
        self.assertIn("details", body)


if __name__ == "__main__":
    unittest.main()
