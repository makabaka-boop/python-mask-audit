"""路由层：/api/v1 下的全部 HTTP 接口。"""

from flask import Blueprint, current_app, jsonify, request

from . import repositories as repo
from .audit_queries import group_history, rule_history, sample_history
from .conflicts import detect_conflicts
from .errors import validation_error
from .executor import execute_rules, validate_rule_payload
from .selfcheck import run_selfcheck
from .snapshot import build_snapshot, classify_changes, diff_rules

api_blueprint = Blueprint("api", __name__, url_prefix="/api/v1")


def _db():
    return current_app.extensions["db"]


def _body() -> dict:
    data = request.get_json(silent=True)
    if data is None:
        raise validation_error("请求体必须是 JSON")
    return data


def _ok(data, status: int = 200):
    return jsonify(data), status


def _resolve_input(data: dict):
    """从 sample_id 或 input_text 解析输入文本，返回 (sample_id, text)。"""
    sample_id = data.get("sample_id")
    input_text = data.get("input_text")
    if sample_id is not None:
        sample = repo.get_sample(_db(), int(sample_id))
        return sample["id"], sample["raw_text"]
    if not input_text or not isinstance(input_text, str):
        raise validation_error("必须提供 sample_id 或 input_text")
    return None, input_text


def _persist_run(sample_id, rule_id, group_id, input_text, rules):
    """执行规则并落库：演练记录 + 命中明细 + 规则快照。"""
    db = _db()
    output_text, hits = execute_rules(input_text, rules)
    hit_count = sum(h["matched_count"] for h in hits)
    run_id = repo.create_run(db, sample_id, rule_id, group_id,
                             input_text, output_text, hit_count)
    for h in hits:
        if h["matched_count"] > 0:
            repo.add_hit_detail(db, run_id, h)
    repo.save_snapshot(db, run_id, build_snapshot(rules))
    return run_id, output_text, hit_count, hits


# ---------- 健康检查 ----------

@api_blueprint.get("/health")
def health():
    _db().query_one("SELECT 1")
    return _ok({"status": "ok"})


# ---------- 规则管理 ----------

@api_blueprint.post("/rules")
def create_rule():
    fields = validate_rule_payload(_body())
    rule = repo.create_rule(_db(), fields)
    repo.add_audit(_db(), "create_rule", "rule", rule["id"],
                   {"rule_name": rule["rule_name"]})
    return _ok(rule, 201)


@api_blueprint.get("/rules")
def list_rules():
    return _ok({"rules": repo.list_rules(_db())})


@api_blueprint.get("/rules/<int:rule_id>")
def get_rule(rule_id):
    return _ok(repo.get_rule(_db(), rule_id))


@api_blueprint.patch("/rules/<int:rule_id>/status")
def toggle_rule(rule_id):
    data = _body()
    if "enabled" not in data or not isinstance(data["enabled"], bool):
        raise validation_error("enabled 必须是布尔值")
    rule = repo.set_rule_enabled(_db(), rule_id, data["enabled"])
    repo.add_audit(_db(), "toggle_rule", "rule", rule_id,
                   {"enabled": data["enabled"]})
    return _ok(rule)


@api_blueprint.patch("/rules/<int:rule_id>/priority")
def change_priority(rule_id):
    data = _body()
    if not isinstance(data.get("priority"), int):
        raise validation_error("priority 必须是整数")
    rule = repo.set_rule_priority(_db(), rule_id, data["priority"])
    repo.add_audit(_db(), "change_priority", "rule", rule_id,
                   {"priority": data["priority"]})
    return _ok(rule)


# ---------- 分组管理 ----------

@api_blueprint.post("/groups")
def create_group():
    data = _body()
    group_name = data.get("group_name")
    if not group_name or not isinstance(group_name, str):
        raise validation_error("group_name 不能为空")
    group = repo.create_group(_db(), group_name.strip(), str(data.get("description", "")))
    repo.add_audit(_db(), "create_group", "group", group["id"],
                   {"group_name": group["group_name"]})
    return _ok(group, 201)


@api_blueprint.get("/groups")
def list_groups():
    return _ok({"groups": repo.list_groups(_db())})


@api_blueprint.get("/groups/<int:group_id>/rules")
def list_group_rules(group_id):
    rules = repo.list_group_rules(_db(), group_id)
    return _ok({"group_id": group_id, "rules": rules})


@api_blueprint.post("/groups/<int:group_id>/rules")
def add_group_rule(group_id):
    data = _body()
    rule_id = data.get("rule_id")
    if not isinstance(rule_id, int):
        raise validation_error("rule_id 必须是整数")
    result = repo.add_group_rule(_db(), group_id, rule_id)
    repo.add_audit(_db(), "group_add_rule", "group", group_id, {"rule_id": rule_id})
    return _ok(result, 201)


@api_blueprint.delete("/groups/<int:group_id>/rules/<int:rule_id>")
def remove_group_rule(group_id, rule_id):
    repo.remove_group_rule(_db(), group_id, rule_id)
    repo.add_audit(_db(), "group_remove_rule", "group", group_id, {"rule_id": rule_id})
    return _ok({"group_id": group_id, "rule_id": rule_id, "removed": True})


@api_blueprint.get("/groups/<int:group_id>/conflicts")
def group_conflicts(group_id):
    """规则冲突检测：只返回风险提示，不阻止保存/加入分组/执行演练。"""
    rules = repo.list_group_rules(_db(), group_id)
    conflicts = detect_conflicts(rules)
    repo.add_audit(_db(), "conflict_check", "group", group_id,
                   {"conflict_count": len(conflicts)})
    return _ok({"group_id": group_id, "conflict_count": len(conflicts),
                "conflicts": conflicts})


# ---------- 样例管理 ----------

@api_blueprint.post("/samples")
def create_sample():
    data = _body()
    if not data.get("sample_name"):
        raise validation_error("sample_name 不能为空")
    if not data.get("raw_text") or not isinstance(data.get("raw_text"), str):
        raise validation_error("raw_text 不能为空")
    sample = repo.create_sample(_db(), data)
    repo.add_audit(_db(), "create_sample", "sample", sample["id"],
                   {"sample_name": sample["sample_name"]})
    return _ok(sample, 201)


@api_blueprint.get("/samples")
def list_samples():
    return _ok({"samples": repo.list_samples(_db())})


# ---------- 演练执行 ----------

@api_blueprint.post("/rules/<int:rule_id>/execute")
def execute_single_rule(rule_id):
    rule = repo.get_rule(_db(), rule_id)
    if not rule["enabled"]:
        raise validation_error("禁用规则不能参与演练", {"rule_id": rule_id})
    sample_id, input_text = _resolve_input(_body())
    run_id, output_text, hit_count, _ = _persist_run(
        sample_id, rule_id, None, input_text, [rule])
    repo.add_audit(_db(), "execute_run", "run", run_id,
                   {"mode": "single_rule", "rule_id": rule_id})
    return _ok({"run_id": run_id, "input_text": input_text,
                "output_text": output_text, "hit_count": hit_count})


@api_blueprint.post("/groups/<int:group_id>/execute")
def execute_group(group_id):
    repo.get_group(_db(), group_id)
    rules = repo.list_group_rules(_db(), group_id, only_enabled=True)
    if not rules:
        raise validation_error("分组内没有已启用的规则", {"group_id": group_id})
    sample_id, input_text = _resolve_input(_body())
    run_id, output_text, hit_count, _ = _persist_run(
        sample_id, None, group_id, input_text, rules)
    repo.add_audit(_db(), "execute_run", "run", run_id,
                   {"mode": "group", "group_id": group_id,
                    "rule_ids": [r["id"] for r in rules]})
    return _ok({"run_id": run_id, "input_text": input_text,
                "output_text": output_text, "hit_count": hit_count,
                "executed_rule_ids": [r["id"] for r in rules]})


# ---------- 演练明细 / 快照 / 统计 ----------

@api_blueprint.get("/runs/<int:run_id>")
def get_run(run_id):
    run = repo.get_run(_db(), run_id)
    run["hit_details"] = repo.list_hit_details(_db(), run_id)
    return _ok(run)


@api_blueprint.get("/runs/<int:run_id>/snapshot")
def get_run_snapshot(run_id):
    repo.get_run(_db(), run_id)
    return _ok({"run_id": run_id, "rule_snapshots": repo.get_snapshot(_db(), run_id)})


@api_blueprint.get("/rules/<int:rule_id>/stats")
def rule_stats(rule_id):
    return _ok(repo.rule_hit_stats(_db(), rule_id))


# ---------- 脱敏预览（不写入演练记录） ----------

@api_blueprint.post("/preview")
def preview():
    data = _body()
    _, input_text = _resolve_input(data)
    db = _db()

    if data.get("group_id") is not None:
        rules = repo.list_group_rules(db, int(data["group_id"]), only_enabled=True)
    elif data.get("rule_ids"):
        rules = [repo.get_rule(db, int(rid)) for rid in data["rule_ids"]]
        rules = [r for r in rules if r["enabled"]]
    else:
        raise validation_error("必须提供 group_id 或 rule_ids")
    if not rules:
        raise validation_error("没有可执行的启用规则")

    output_text, hits = execute_rules(input_text, rules)
    hit_count = sum(h["matched_count"] for h in hits)
    # 预览写审计事件，但不写演练记录和命中明细
    repo.add_audit(db, "preview", "preview", None,
                   {"group_id": data.get("group_id"),
                    "rule_ids": [r["id"] for r in rules],
                    "hit_count": hit_count})
    return _ok({"input_text": input_text, "output_text": output_text,
                "hit_count": hit_count,
                "hit_details": [h for h in hits if h["matched_count"] > 0]})


# ---------- 回归验证 ----------

@api_blueprint.post("/regression")
def regression():
    """回归验证：基于最近一次演练的规则快照，用当前分组成员重跑同样输入。

    - 只传 sample_id 时，自动定位该样例最近一次使用的规则分组；
    - 传 group_id（可叠加 sample_id）时，定位该分组的最近一次演练。
    结果不一致时，diff_sources 说明差异来自分组成员变化、优先级变化、
    替换配置变化还是规则配置变化（全部基于快照字段对比，不只看最终文本）。
    """
    data = _body()
    group_id = data.get("group_id")
    sample_id = data.get("sample_id")
    if group_id is None and sample_id is None:
        raise validation_error("必须提供 sample_id 或 group_id")
    db = _db()

    if group_id is None:
        last_run = repo.find_latest_group_run_for_sample(db, int(sample_id))
        group_id = last_run["group_id"]
    else:
        group_id = int(group_id)
        last_run = repo.find_latest_run(
            db, group_id=group_id,
            sample_id=int(sample_id) if sample_id is not None else None)

    snapshot_rows = repo.get_snapshot(db, last_run["id"])

    # 与全部分组成员（含禁用）对比快照，禁用会体现为 enabled 字段变化而非成员缺失
    member_rules = repo.list_group_rules(db, group_id)
    enabled_rules = [r for r in member_rules if r["enabled"]]
    changes = diff_rules(snapshot_rows, member_rules)
    diff_sources = classify_changes(changes)

    # 用快照时的输入文本，按当前启用规则重跑
    rerun_output, rerun_hits = execute_rules(last_run["input_text"], enabled_rules)
    rerun_hit_count = sum(h["matched_count"] for h in rerun_hits)
    output_changed = rerun_output != last_run["output_text"]
    passed = not changes and not output_changed

    repo.add_audit(db, "regression_check", "run", last_run["id"],
                   {"group_id": group_id, "sample_id": last_run["sample_id"],
                    "change_count": len(changes), "output_changed": output_changed,
                    "passed": passed})
    return _ok({
        "base_run_id": last_run["id"],
        "sample_id": last_run["sample_id"],
        "group_id": group_id,
        "snapshot_rule_ids": [s["rule_id"] for s in snapshot_rows],
        "rule_changes": changes,
        "diff_sources": diff_sources,
        "output_changed": output_changed,
        "previous_output_text": last_run["output_text"],
        "rerun_output_text": rerun_output,
        "previous_hit_count": last_run["hit_count"],
        "rerun_hit_count": rerun_hit_count,
        "passed": not changes and not output_changed,
    })


# ---------- 审计事件 ----------

@api_blueprint.get("/audits")
def list_audits():
    limit = request.args.get("limit", 100, type=int)
    return _ok({"audits": repo.list_audits(_db(), limit)})


# ---------- 审计查询（规则 / 样例 / 分组三维度） ----------

@api_blueprint.get("/audit/rules/<int:rule_id>")
def audit_rule(rule_id):
    return _ok(rule_history(_db(), rule_id))


@api_blueprint.get("/audit/samples/<int:sample_id>")
def audit_sample(sample_id):
    return _ok(sample_history(_db(), sample_id))


@api_blueprint.get("/audit/groups/<int:group_id>")
def audit_group(group_id):
    return _ok(group_history(_db(), group_id))


# ---------- 一致性自检 ----------

@api_blueprint.get("/selfcheck")
def selfcheck():
    """审计链路一致性自检：只读检查，不修改任何数据。"""
    result = run_selfcheck(_db())
    repo.add_audit(_db(), "selfcheck", "selfcheck", None,
                   {"passed": result["passed"], "failed_count": result["failed_count"]})
    return _ok(result)
