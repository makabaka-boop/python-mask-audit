"""链路一致性自检路由。"""
from flask import Blueprint, jsonify

from ..consistency import run_all_checks

consistency_bp = Blueprint(
    "consistency", __name__, url_prefix="/api/v1/consistency"
)


@consistency_bp.get("/checks")
def consistency_checks():
    """检查审计链路断点，返回每个检查项的通过状态与问题明细。"""
    return jsonify(run_all_checks())
