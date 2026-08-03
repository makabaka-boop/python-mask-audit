"""路由与请求处理。

将 HTTP 请求分发到对应处理函数。所有路径以 ``/api/v1`` 开头，
返回 ``(status_code, body_dict)``。
"""

import re

from . import audit_queries, config, executor, repositories as repo, selfcheck, snapshot
from .errors import NotFoundError, RouteNotFoundError, ValidationError


# --------------------------------------------------------------------------- #
# 演练 / 预览 / 回归 核心逻辑
# --------------------------------------------------------------------------- #
def _resolve_input_text(conn, payload):
    """确定演练输入文本：优先 input_text，其次样例 raw_text。"""
    sample_id = payload.get("sample_id")
    input_text = payload.get("input_text")
    if input_text is None and sample_id is not None:
        sample = repo.get_sample(conn, sample_id)
        input_text = sample["raw_text"]
    if input_text is None:
        raise ValidationError("必须提供 input_text 或 sample_id", details={})
    return sample_id, input_text


def run_single_rule(conn, payload):
    """执行单条规则并写入演练记录。"""
    rule_id = payload.get("rule_id")
    if rule_id is None:
        raise ValidationError("rule_id 不能为空", details={"field": "rule_id"})
    rule = repo.get_rule(conn, rule_id)
    if not rule["enabled"]:
        raise ValidationError("禁用规则不能执行", details={"rule_id": rule_id})
    sample_id, input_text = _resolve_input_text(conn, payload)

    # 用 Row 兼容映射构造执行用规则。
    exec_rule = _rule_for_exec(rule)
    output, hits, before, after = executor.execute_rule(exec_rule, input_text)
    hit_details = []
    if hits > 0:
        hit_details.append(
            {
                "rule_id": rule_id,
                "matched_count": hits,
                "before_fragment": before,
                "after_fragment": after,
            }
        )
    snapshots = snapshot.build_snapshots([_rule_for_snapshot(rule)])
    run = repo.create_run(
        conn,
        sample_id=sample_id,
        rule_id=rule_id,
        group_id=None,
        input_text=input_text,
        output_text=output,
        hit_count=hits,
        hit_details=hit_details,
        snapshots=snapshots,
    )
    run["hit_details"] = repo.get_run_hits(conn, run["id"])
    run["rule_snapshots"] = repo.get_run_snapshots(conn, run["id"])
    return run


def run_group(conn, payload):
    """按分组执行演练，仅启用规则参与，按优先级顺序应用。"""
    group_id = payload.get("group_id")
    if group_id is None:
        raise ValidationError("group_id 不能为空", details={"field": "group_id"})
    repo.get_group(conn, group_id)
    sample_id, input_text = _resolve_input_text(conn, payload)

    rule_rows = repo.get_group_enabled_rules(conn, group_id)
    exec_rules = [_rule_for_exec(repo.rule_to_dict(r)) for r in rule_rows]
    output, total_hits, hit_details = executor.execute_rules(exec_rules, input_text)
    snapshots = snapshot.build_snapshots([_rule_for_snapshot(repo.rule_to_dict(r)) for r in rule_rows])
    run = repo.create_run(
        conn,
        sample_id=sample_id,
        rule_id=None,
        group_id=group_id,
        input_text=input_text,
        output_text=output,
        hit_count=total_hits,
        hit_details=hit_details,
        snapshots=snapshots,
    )
    run["hit_details"] = repo.get_run_hits(conn, run["id"])
    run["rule_snapshots"] = repo.get_run_snapshots(conn, run["id"])
    return run


def preview(conn, payload):
    """脱敏预览：只返回结果和命中明细，不写入演练记录。"""
    _, input_text = _resolve_input_text(conn, payload)
    rule_id = payload.get("rule_id")
    group_id = payload.get("group_id")

    if rule_id is not None:
        rule = repo.get_rule(conn, rule_id)
        if not rule["enabled"]:
            raise ValidationError("禁用规则不能执行", details={"rule_id": rule_id})
        output, hits, before, after = executor.execute_rule(_rule_for_exec(rule), input_text)
        hit_details = []
        if hits > 0:
            hit_details.append(
                {
                    "rule_id": rule_id,
                    "matched_count": hits,
                    "before_fragment": before,
                    "after_fragment": after,
                }
            )
    elif group_id is not None:
        repo.get_group(conn, group_id)
        rule_rows = repo.get_group_enabled_rules(conn, group_id)
        exec_rules = [_rule_for_exec(repo.rule_to_dict(r)) for r in rule_rows]
        output, hits, hit_details = executor.execute_rules(exec_rules, input_text)
    else:
        raise ValidationError("必须提供 rule_id 或 group_id", details={})

    repo.write_audit(conn, "preview", "preview", None, {"rule_id": rule_id, "group_id": group_id, "hit_count": hits})
    return {"input_text": input_text, "output_text": output, "hit_count": hits, "hit_details": hit_details}


def regression(conn, payload):
    """回归验证。

    对某个样例，重新执行它最近一次使用过的规则分组，并将当前结果与历史
    结果比较是否一致。差异归因必须复用首轮定义的规则快照（不允许只比较
    最终文本），归类为四种来源：

    * ``rule_config_change``   —— 规则本身的核心配置变化（match_type/match_value/enabled 等）。
    * ``member_change``        —— 分组成员较首轮发生增删。
    * ``priority_change``      —— 规则优先级较首轮变化。
    * ``replace_config_change``—— 替换策略或替换配置较首轮变化。
    """
    sample_id = payload.get("sample_id")
    if sample_id is None:
        raise ValidationError("sample_id 不能为空", details={"field": "sample_id"})
    repo.get_sample(conn, sample_id)

    # 定位样例最近一次「使用分组」的演练记录。
    last_run = repo.latest_group_run_for_sample(conn, sample_id)
    if last_run is None:
        raise NotFoundError(
            "该样例没有基于分组的历史演练记录", details={"sample_id": sample_id}
        )
    group_id = last_run["group_id"]
    input_text = last_run["input_text"]

    # 首轮快照：回归比较的基线，逐规则封存了 enabled/priority/match_type/
    # replace_strategy/replace_config 等配置。
    baseline_snapshots = repo.get_run_snapshots(conn, last_run["id"])
    baseline_by_id = {s["rule_id"]: s for s in baseline_snapshots}

    # 当前分组中启用的规则（按优先级），构成本轮参与执行的规则集合。
    current_rows = repo.get_group_enabled_rules(conn, group_id)
    current_rules = [repo.rule_to_dict(r) for r in current_rows]
    current_by_id = {r["id"]: r for r in current_rules}

    differences = []

    # 1) 成员变化：对比首轮快照规则集合与当前启用规则集合。
    baseline_ids = set(baseline_by_id)
    current_ids = set(current_by_id)
    for rid in sorted(baseline_ids - current_ids):
        differences.append(
            {
                "rule_id": rid,
                "difference_type": "member_change",
                "message": f"规则 {rid} 参与了首轮演练，但当前已不在分组的启用规则中",
                "before": {"in_run": True},
                "after": {"in_run": False},
            }
        )
    for rid in sorted(current_ids - baseline_ids):
        differences.append(
            {
                "rule_id": rid,
                "difference_type": "member_change",
                "message": f"规则 {rid} 未参与首轮演练，但当前已加入分组的启用规则",
                "before": {"in_run": False},
                "after": {"in_run": True},
            }
        )

    # 2) 对共同规则逐字段归因（复用首轮快照，而非仅比较最终文本）。
    for rid in sorted(baseline_ids & current_ids):
        snap = baseline_by_id[rid]
        cur = current_by_id[rid]
        differences.extend(_attribute_rule_diff(rid, snap, cur))

    # 历史结果直接取自首轮演练记录（已随快照一并封存）；当前结果用当前
    # 启用规则重新执行。差异说明来自上面对首轮快照的逐字段比较，而非仅
    # 比较两段最终文本。
    current_exec = [_rule_for_exec(r) for r in current_rules]
    current_output, current_hits, _ = executor.execute_rules(current_exec, input_text)

    output_consistent = current_output == last_run["output_text"]
    consistent = output_consistent and not differences

    repo.write_audit(
        conn,
        "regression",
        "sample",
        sample_id,
        {
            "baseline_run_id": last_run["id"],
            "group_id": group_id,
            "consistent": consistent,
        },
    )
    return {
        "sample_id": sample_id,
        "group_id": group_id,
        "baseline_run_id": last_run["id"],
        "baseline_output": last_run["output_text"],
        "baseline_hit_count": last_run["hit_count"],
        "current_output": current_output,
        "current_hit_count": current_hits,
        "output_consistent": output_consistent,
        "consistent": consistent,
        "differences": differences,
    }


def _attribute_rule_diff(rule_id, snap, current):
    """将某条规则首轮快照与当前配置的差异归因为具体来源类别。"""
    diffs = []

    if snap.get("priority") != current.get("priority"):
        diffs.append(
            {
                "rule_id": rule_id,
                "difference_type": "priority_change",
                "message": f"规则 {rule_id} 优先级由 {snap.get('priority')} 变为 {current.get('priority')}",
                "before": snap.get("priority"),
                "after": current.get("priority"),
            }
        )

    if (
        snap.get("replace_strategy") != current.get("replace_strategy")
        or snap.get("replace_config") != current.get("replace_config")
    ):
        diffs.append(
            {
                "rule_id": rule_id,
                "difference_type": "replace_config_change",
                "message": f"规则 {rule_id} 的替换策略或替换配置较首轮发生变化",
                "before": {
                    "replace_strategy": snap.get("replace_strategy"),
                    "replace_config": snap.get("replace_config"),
                },
                "after": {
                    "replace_strategy": current.get("replace_strategy"),
                    "replace_config": current.get("replace_config"),
                },
            }
        )

    # 规则核心配置变化（匹配方式、启用状态等，替换相关已单列）。
    core_before = {}
    core_after = {}
    for f in ("enabled", "match_type"):
        if snap.get(f) != current.get(f):
            core_before[f] = snap.get(f)
            core_after[f] = current.get(f)
    if core_before:
        diffs.append(
            {
                "rule_id": rule_id,
                "difference_type": "rule_config_change",
                "message": f"规则 {rule_id} 的核心配置较首轮发生变化",
                "before": core_before,
                "after": core_after,
            }
        )

    return diffs


def _rule_for_exec(rule):
    """构造执行器所需的规则映射。"""
    return {
        "id": rule["id"],
        "match_type": rule["match_type"],
        "match_value": rule["match_value"],
        "replace_strategy": rule["replace_strategy"],
        "replace_config": rule["replace_config"],
    }


def _rule_for_snapshot(rule):
    return {
        "id": rule["id"],
        "rule_name": rule["rule_name"],
        "enabled": rule["enabled"],
        "priority": rule["priority"],
        "match_type": rule["match_type"],
        "replace_strategy": rule["replace_strategy"],
        "replace_config": rule["replace_config"],
    }


# --------------------------------------------------------------------------- #
# 路由表
# --------------------------------------------------------------------------- #
# 每个条目为 (method, 正则, handler)。handler(conn, match, payload) -> (status, body)
ROUTES = []


def route(method, pattern):
    compiled = re.compile("^" + config.API_PREFIX + pattern + "$")

    def deco(fn):
        ROUTES.append((method, compiled, fn))
        return fn

    return deco


# ---- 健康检查 ---- #
@route("GET", r"/health")
def h_health(conn, m, payload):
    return 200, {"status": "ok", "service": "mask-audit", "port": config.PORT}


# ---- 规则 ---- #
@route("POST", r"/rules")
def h_create_rule(conn, m, payload):
    return 201, repo.create_rule(conn, payload)


@route("GET", r"/rules")
def h_list_rules(conn, m, payload):
    return 200, {"items": repo.list_rules(conn)}


@route("GET", r"/rules/(?P<rule_id>\d+)")
def h_get_rule(conn, m, payload):
    return 200, repo.get_rule(conn, int(m.group("rule_id")))


@route("POST", r"/rules/(?P<rule_id>\d+)/enable")
def h_enable_rule(conn, m, payload):
    return 200, repo.set_rule_enabled(conn, int(m.group("rule_id")), True)


@route("POST", r"/rules/(?P<rule_id>\d+)/disable")
def h_disable_rule(conn, m, payload):
    return 200, repo.set_rule_enabled(conn, int(m.group("rule_id")), False)


@route("POST", r"/rules/(?P<rule_id>\d+)/priority")
def h_priority(conn, m, payload):
    priority = payload.get("priority")
    return 200, repo.update_rule_priority(conn, int(m.group("rule_id")), priority)


@route("GET", r"/rules/(?P<rule_id>\d+)/stats")
def h_rule_stats(conn, m, payload):
    return 200, repo.rule_hit_stats(conn, int(m.group("rule_id")))


# ---- 分组 ---- #
@route("POST", r"/groups")
def h_create_group(conn, m, payload):
    return 201, repo.create_group(conn, payload)


@route("GET", r"/groups")
def h_list_groups(conn, m, payload):
    return 200, {"items": repo.list_groups(conn)}


@route("GET", r"/groups/(?P<group_id>\d+)/members")
def h_list_members(conn, m, payload):
    return 200, {"items": repo.list_group_members(conn, int(m.group("group_id")))}


@route("POST", r"/groups/(?P<group_id>\d+)/members")
def h_add_member(conn, m, payload):
    rule_id = payload.get("rule_id")
    if rule_id is None:
        raise ValidationError("rule_id 不能为空", details={"field": "rule_id"})
    members = repo.add_group_member(conn, int(m.group("group_id")), int(rule_id))
    return 201, {"items": members}


@route("DELETE", r"/groups/(?P<group_id>\d+)/members/(?P<rule_id>\d+)")
def h_remove_member(conn, m, payload):
    members = repo.remove_group_member(conn, int(m.group("group_id")), int(m.group("rule_id")))
    return 200, {"items": members}


@route("GET", r"/groups/(?P<group_id>\d+)/conflicts")
def h_group_conflicts(conn, m, payload):
    conflicts = repo.detect_group_conflicts(conn, int(m.group("group_id")))
    return 200, {"items": conflicts}


# ---- 样例 ---- #
@route("POST", r"/samples")
def h_create_sample(conn, m, payload):
    return 201, repo.create_sample(conn, payload)


@route("GET", r"/samples")
def h_list_samples(conn, m, payload):
    return 200, {"items": repo.list_samples(conn)}


@route("GET", r"/samples/(?P<sample_id>\d+)")
def h_get_sample(conn, m, payload):
    return 200, repo.get_sample(conn, int(m.group("sample_id")))


# ---- 演练 ---- #
@route("POST", r"/runs/rule")
def h_run_rule(conn, m, payload):
    return 201, run_single_rule(conn, payload)


@route("POST", r"/runs/group")
def h_run_group(conn, m, payload):
    return 201, run_group(conn, payload)


@route("GET", r"/runs")
def h_list_runs(conn, m, payload):
    return 200, {"items": repo.list_runs(conn)}


@route("GET", r"/runs/(?P<run_id>\d+)")
def h_run_detail(conn, m, payload):
    return 200, repo.get_run_detail(conn, int(m.group("run_id")))


@route("GET", r"/runs/(?P<run_id>\d+)/snapshots")
def h_run_snapshots(conn, m, payload):
    repo.get_run(conn, int(m.group("run_id")))
    return 200, {"items": repo.get_run_snapshots(conn, int(m.group("run_id")))}


# ---- 预览 / 回归 ---- #
@route("POST", r"/preview")
def h_preview(conn, m, payload):
    return 200, preview(conn, payload)


@route("POST", r"/regression")
def h_regression(conn, m, payload):
    return 200, regression(conn, payload)


# ---- 审计 ---- #
@route("GET", r"/audit/events")
def h_audit(conn, m, payload):
    return 200, {"items": repo.list_audit_events(conn)}


@route("GET", r"/audit/rules/(?P<rule_id>\d+)")
def h_audit_rule(conn, m, payload):
    return 200, audit_queries.rule_audit(conn, int(m.group("rule_id")))


@route("GET", r"/audit/samples/(?P<sample_id>\d+)")
def h_audit_sample(conn, m, payload):
    return 200, audit_queries.sample_audit(conn, int(m.group("sample_id")))


@route("GET", r"/audit/groups/(?P<group_id>\d+)")
def h_audit_group(conn, m, payload):
    return 200, audit_queries.group_audit(conn, int(m.group("group_id")))


# ---- 一致性自检 ---- #
@route("GET", r"/selfcheck")
def h_selfcheck(conn, m, payload):
    return 200, selfcheck.run_selfcheck(conn)


def dispatch(conn, method, path, payload):
    """按方法与路径分发请求。"""
    matched_path = False
    for rmethod, pattern, fn in ROUTES:
        m = pattern.match(path)
        if m:
            matched_path = True
            if rmethod == method:
                return fn(conn, m, payload or {})
    if matched_path:
        from .errors import MethodNotAllowedError

        raise MethodNotAllowedError("方法不被允许", details={"method": method, "path": path})
    raise RouteNotFoundError("路由不存在", details={"method": method, "path": path})
