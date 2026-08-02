"""一致性自检。

交付前用于确认脱敏审计链路没有断点。逐项检查数据一致性，返回统一
JSON：顶层 ``passed`` 表示整体是否通过，``checks`` 数组逐项列出检查
名称、通过状态、问题数量与明细。

检查项：

1. ``orphan_hit_details``          —— 孤立命中明细（run_id 找不到对应演练记录）。
2. ``group_run_missing_snapshot``  —— 分组演练缺失规则快照。
3. ``hit_detail_snapshot_mismatch``—— 命中明细的规则与该演练的快照无法对应。
4. ``preview_leaked_into_runs``    —— 预览数据误落库（既无 rule_id 又无 group_id 的演练记录）。
5. ``disabled_rule_in_run``        —— 禁用规则参与了演练（快照中 enabled=0）。
6. ``invalid_regex_rules``         —— 非法正则残留（regex 规则 match_value 无法编译）。
7. ``regression_missing_baseline`` —— 回归验证缺少历史基准（baseline_run_id 指向不存在的演练）。
"""

import json
import re


def _check(name, problems):
    return {
        "name": name,
        "passed": len(problems) == 0,
        "problem_count": len(problems),
        "problems": problems,
    }


def _orphan_hit_details(conn):
    rows = conn.execute(
        """SELECT h.id AS id, h.run_id AS run_id
           FROM hit_details h LEFT JOIN runs r ON r.id = h.run_id
           WHERE r.id IS NULL ORDER BY h.id ASC"""
    ).fetchall()
    return [{"hit_detail_id": r["id"], "run_id": r["run_id"]} for r in rows]


def _group_run_missing_snapshot(conn):
    # 分组演练一旦产生命中明细，就说明有规则参与执行，必须存在对应快照。
    # 全部规则被禁用/无命中的空演练没有快照属正常，不算断点。
    rows = conn.execute(
        """SELECT r.id AS run_id, r.group_id AS group_id
           FROM runs r
           WHERE r.group_id IS NOT NULL
             AND EXISTS (SELECT 1 FROM hit_details h WHERE h.run_id = r.id)
             AND NOT EXISTS (SELECT 1 FROM rule_snapshots s WHERE s.run_id = r.id)
           ORDER BY r.id ASC"""
    ).fetchall()
    return [{"run_id": r["run_id"], "group_id": r["group_id"]} for r in rows]


def _hit_detail_snapshot_mismatch(conn):
    rows = conn.execute(
        """SELECT h.id AS hit_id, h.run_id AS run_id, h.rule_id AS rule_id
           FROM hit_details h
           WHERE NOT EXISTS (
               SELECT 1 FROM rule_snapshots s
               WHERE s.run_id = h.run_id AND s.rule_id = h.rule_id
           )
           ORDER BY h.id ASC"""
    ).fetchall()
    return [
        {"hit_detail_id": r["hit_id"], "run_id": r["run_id"], "rule_id": r["rule_id"]}
        for r in rows
    ]


def _preview_leaked_into_runs(conn):
    # 单条执行写 rule_id，分组执行写 group_id；两者皆空的演练记录属异常，
    # 通常意味着预览数据误落库。
    rows = conn.execute(
        "SELECT id FROM runs WHERE rule_id IS NULL AND group_id IS NULL ORDER BY id ASC"
    ).fetchall()
    return [{"run_id": r["id"]} for r in rows]


def _disabled_rule_in_run(conn):
    rows = conn.execute(
        """SELECT s.id AS snapshot_id, s.run_id AS run_id, s.rule_id AS rule_id
           FROM rule_snapshots s
           JOIN runs r ON r.id = s.run_id
           WHERE s.enabled = 0 AND r.group_id IS NOT NULL
           ORDER BY s.id ASC"""
    ).fetchall()
    return [
        {"snapshot_id": r["snapshot_id"], "run_id": r["run_id"], "rule_id": r["rule_id"]}
        for r in rows
    ]


def _invalid_regex_rules(conn):
    rows = conn.execute(
        "SELECT id, match_value FROM rules WHERE match_type='regex' ORDER BY id ASC"
    ).fetchall()
    problems = []
    for r in rows:
        try:
            re.compile(r["match_value"])
        except re.error as exc:
            problems.append({"rule_id": r["id"], "reason": str(exc)})
    return problems


def _regression_missing_baseline(conn):
    rows = conn.execute(
        """SELECT id, detail FROM audit_events
           WHERE event_type='regression' ORDER BY id ASC"""
    ).fetchall()
    problems = []
    for r in rows:
        detail = json.loads(r["detail"] or "{}")
        baseline_run_id = detail.get("baseline_run_id")
        if baseline_run_id is None:
            problems.append({"event_id": r["id"], "reason": "缺少 baseline_run_id"})
            continue
        exists = conn.execute("SELECT 1 FROM runs WHERE id=?", (baseline_run_id,)).fetchone()
        if not exists:
            problems.append(
                {
                    "event_id": r["id"],
                    "baseline_run_id": baseline_run_id,
                    "reason": "baseline_run_id 指向的演练记录不存在",
                }
            )
    return problems


CHECKS = [
    ("orphan_hit_details", _orphan_hit_details),
    ("group_run_missing_snapshot", _group_run_missing_snapshot),
    ("hit_detail_snapshot_mismatch", _hit_detail_snapshot_mismatch),
    ("preview_leaked_into_runs", _preview_leaked_into_runs),
    ("disabled_rule_in_run", _disabled_rule_in_run),
    ("invalid_regex_rules", _invalid_regex_rules),
    ("regression_missing_baseline", _regression_missing_baseline),
]


def run_selfcheck(conn):
    """执行全部一致性检查，返回统一 JSON。"""
    checks = [_check(name, fn(conn)) for name, fn in CHECKS]
    total_problems = sum(c["problem_count"] for c in checks)
    return {
        "passed": total_problems == 0,
        "total_problems": total_problems,
        "checks": checks,
    }
