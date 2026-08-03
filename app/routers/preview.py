"""脱敏预览路由（不写演练记录）。"""
from flask import Blueprint, jsonify, request

from ..errors import ValidationError
from ..services import MaskService

preview_bp = Blueprint("preview", __name__, url_prefix="/api/v1/preview")


def _service() -> MaskService:
    return MaskService()


@preview_bp.post("/rule/<int:rule_id>")
def preview_rule(rule_id: int):
    payload = request.get_json(silent=True) or {}
    text = payload.get("text")
    if text is None or not isinstance(text, str):
        raise ValidationError("text 不能为空", details={"field": "text"})
    return jsonify(_service().preview_single_rule(rule_id, text))


@preview_bp.post("/group/<int:group_id>")
def preview_group(group_id: int):
    payload = request.get_json(silent=True) or {}
    text = payload.get("text")
    if text is None or not isinstance(text, str):
        raise ValidationError("text 不能为空", details={"field": "text"})
    return jsonify(_service().preview_group(group_id, text))
