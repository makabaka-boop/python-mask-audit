"""审计查询路由：按规则、样例、分组三个维度聚合演练历史。"""
from flask import Blueprint, jsonify

from ..services import MaskService

audit_bp = Blueprint("audit", __name__, url_prefix="/api/v1/audit")


def _service() -> MaskService:
    return MaskService()


@audit_bp.get("/rules/<int:rule_id>")
def audit_by_rule(rule_id: int):
    """规则维度：当前配置、历史快照版本、命中统计、最近命中时间、事件。"""
    return jsonify(_service().audit_by_rule(rule_id))


@audit_bp.get("/samples/<int:sample_id>")
def audit_by_sample(sample_id: int):
    """样例维度：最近演练、最近回归、各规则命中分布、事件。"""
    return jsonify(_service().audit_by_sample(sample_id))


@audit_bp.get("/groups/<int:group_id>")
def audit_by_group(group_id: int):
    """分组维度：当前成员、历史快照成员、成员变化摘要、最近演练。"""
    return jsonify(_service().audit_by_group(group_id))
