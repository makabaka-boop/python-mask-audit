"""回归验证路由。"""
from flask import Blueprint, jsonify, request

from ..services import MaskService

regression_bp = Blueprint("regression", __name__, url_prefix="/api/v1/regression")


def _service() -> MaskService:
    return MaskService()


@regression_bp.get("")
def regression_check():
    run_id = request.args.get("run_id", type=int)
    sample_id = request.args.get("sample_id", type=int)
    group_id = request.args.get("group_id", type=int)
    result = _service().regression_check(
        sample_id=sample_id, group_id=group_id, run_id=run_id
    )
    return jsonify(result)
