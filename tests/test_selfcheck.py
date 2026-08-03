"""一致性自检、初始化数据可用性、以及所有路由 /api/v1 前缀测试。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.helpers import make_env, ServerFixture


class SelfcheckTestCase(unittest.TestCase):
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
            "priority": 10,
        }
        payload.update(kw)
        _, body = self.srv.request("POST", "/api/v1/rules", payload)
        return body


class TestSelfcheckPass(SelfcheckTestCase):
    def test_healthy_chain_passes(self):
        # 构造一条完整、正常的审计链路。
        r = self._rule(rule_name="ok")
        _, s = self.srv.request("POST", "/api/v1/samples",
                                {"sample_name": "sc", "raw_text": "num 13800001111"})
        _, g = self.srv.request("POST", "/api/v1/groups", {"group_name": "scg"})
        gid = g["id"]
        self.srv.request("POST", f"/api/v1/groups/{gid}/members", {"rule_id": r["id"]})
        self.srv.request("POST", "/api/v1/runs/group", {"group_id": gid, "sample_id": s["id"]})
        # 预览一次，确认不会污染自检
        self.srv.request("POST", "/api/v1/preview", {"rule_id": r["id"], "input_text": "13800001111"})
        # 回归一次，产生带 baseline 的审计事件
        self.srv.request("POST", "/api/v1/regression", {"sample_id": s["id"]})

        status, body = self.srv.request("GET", "/api/v1/selfcheck")
        self.assertEqual(status, 200)
        self.assertTrue(body["passed"], body)
        self.assertEqual(body["total_problems"], 0)
        names = {c["name"] for c in body["checks"]}
        for expected in [
            "orphan_hit_details", "group_run_missing_snapshot",
            "hit_detail_snapshot_mismatch", "preview_leaked_into_runs",
            "disabled_rule_in_run", "invalid_regex_rules",
            "regression_missing_baseline",
        ]:
            self.assertIn(expected, names)


class TestSelfcheckDetectsProblems(SelfcheckTestCase):
    def _conn(self):
        # 直接连库注入异常数据，模拟链路断点；关闭外键以便注入孤立记录。
        from app import db
        conn = db.get_connection(self.db_path)
        conn.execute("PRAGMA foreign_keys = OFF")
        return conn

    def test_detects_injected_anomalies(self):
        r = self._rule(rule_name="anom")
        conn = self._conn()
        try:
            # 孤立命中明细：run_id 指向不存在的演练。
            conn.execute(
                "INSERT INTO hit_details (run_id, rule_id, matched_count) VALUES (99999, ?, 1)",
                (r["id"],),
            )
            # 预览误落库：既无 rule_id 又无 group_id 的演练记录。
            conn.execute(
                "INSERT INTO runs (sample_id, rule_id, group_id, input_text, output_text, hit_count, executed_at) "
                "VALUES (NULL, NULL, NULL, 'x', 'x', 0, '2026-01-01T00:00:00Z')"
            )
            # 非法正则残留：绕过校验直接写入。
            conn.execute(
                "INSERT INTO rules (rule_name, field_type, match_type, match_value, replace_strategy, "
                "replace_config, priority, enabled, created_at, updated_at) "
                "VALUES ('bad','x','regex','([a-z','fixed','{}',10,1,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')"
            )
            # 回归缺少历史基准：baseline_run_id 指向不存在的演练。
            conn.execute(
                "INSERT INTO audit_events (event_type, entity_type, entity_id, detail, created_at) "
                "VALUES ('regression','sample',1,'{\"baseline_run_id\": 88888}','2026-01-01T00:00:00Z')"
            )
            conn.commit()
        finally:
            conn.close()

        status, body = self.srv.request("GET", "/api/v1/selfcheck")
        self.assertEqual(status, 200)
        self.assertFalse(body["passed"])
        failed = {c["name"]: c for c in body["checks"] if not c["passed"]}
        self.assertIn("orphan_hit_details", failed)
        self.assertIn("preview_leaked_into_runs", failed)
        self.assertIn("invalid_regex_rules", failed)
        self.assertIn("regression_missing_baseline", failed)
        # 每个失败项都带问题数量与明细
        for c in failed.values():
            self.assertGreater(c["problem_count"], 0)
            self.assertEqual(len(c["problems"]), c["problem_count"])


class TestSeedScript(SelfcheckTestCase):
    def test_seed_creates_working_chain(self):
        # seed 脚本以本测试服务器为目标运行。
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
        import seed as seed_mod

        base = f"http://127.0.0.1:{self.srv.port}"
        result = seed_mod.seed(base)
        self.assertEqual(len(result["rules"]), 2)
        self.assertIsNotNone(result["run_id"])
        # 演练输出应完成脱敏
        self.assertIn("138****1111", result["run_output"])
        self.assertIn("[已脱敏]", result["run_output"])
        self.assertGreaterEqual(result["hit_count"], 2)

        # 初始化数据可用：能查到演练明细与快照
        status, detail = self.srv.request("GET", f"/api/v1/runs/{result['run_id']}")
        self.assertEqual(status, 200)
        self.assertTrue(len(detail["rule_snapshots"]) >= 2)
        # 自检仍通过
        _, sc = self.srv.request("GET", "/api/v1/selfcheck")
        self.assertTrue(sc["passed"], sc)


class TestAllRoutesHavePrefix(unittest.TestCase):
    def test_every_route_starts_with_api_v1(self):
        from app import routes, config
        for method, pattern, _fn in routes.ROUTES:
            self.assertTrue(
                pattern.pattern.startswith("^" + config.API_PREFIX),
                f"路由 {method} {pattern.pattern} 未以 {config.API_PREFIX} 开头",
            )

    def test_new_endpoints_prefixed(self):
        from app import routes
        patterns = [p.pattern for _m, p, _f in routes.ROUTES]
        # 新增接口都应带 /api/v1 前缀
        for needle in ["/selfcheck", "/audit/rules", "/audit/samples",
                       "/audit/groups", "/groups/(?P<group_id>\\d+)/conflicts"]:
            self.assertTrue(
                any(needle in p and p.startswith("^/api/v1") for p in patterns),
                f"未找到带前缀的接口 {needle}",
            )


if __name__ == "__main__":
    unittest.main()
