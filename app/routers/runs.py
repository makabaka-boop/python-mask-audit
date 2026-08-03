"""演练记录路由。"""
from flask import Blueprint, jsonify, request

from ..errors import ValidationError
from ..services import MaskService

runs_bp = Blueprint("runs", __name__, url_prefix="/api/v1/runs")


def _service() -> MaskService:
    return MaskService()


@runs_bp.get("")
def list_runs():
    sample_id = request.args.get("sample_id", type=int)
    rule_id = request.args.get("rule_id", type=int)
    group_id = request.args.get("group_id", type=int)
    limit = request.args.get("limit", default=50, type=int)
    runs = _service().runs.list(
        sample_id=sample_id, rule_id=rule_id, group_id=group_id, limit=limit
    )
    return jsonify({"items": runs, "total": len(runs)})


@runs_bp.get("/<int:run_id>")
def get_run(run_id: int):
    return jsonify(_service().get_run_detail(run_id))


@runs_bp.get("/<int:run_id>/snapshot")
def get_run_snapshot(run_id: int):
    return jsonify(_service().get_run_snapshot(run_id))


@runs_bp.post("/single")
def run_single():
    payload = request.get_json(silent=True) or {}
    rule_id = payload.get("rule_id")
    text = payload.get("text")
    sample_id = payload.get("sample_id")
    if not isinstance(rule_id, int):
        raise ValidationError("rule_id 必须是整数", details={"field": "rule_id"})
    if sample_id is not None:
        sample = _service().samples.get_by_id(sample_id)
        text = sample["raw_text"]
    if text is None or not isinstance(text, str):
        raise ValidationError("text 不能为空", details={"field": "text"})
    return jsonify(
        _service().execute_single_rule(rule_id, text, sample_id=sample_id)
    ), 201


@runs_bp.post("/group")
def run_group():
    payload = request.get_json(silent=True) or {}
    group_id = payload.get("group_id")
    text = payload.get("text")
    sample_id = payload.get("sample_id")
    if not isinstance(group_id, int):
        raise ValidationError("group_id 必须是整数", details={"field": "group_id"})
    if sample_id is None and (text is None or not isinstance(text, str)):
        raise ValidationError(
            "必须提供 sample_id 或 text", details={"field": "text"}
        )
    return jsonify(
        _service().execute_group(group_id, text=text, sample_id=sample_id)
    ), 201
