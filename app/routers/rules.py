"""规则管理路由。"""
from flask import Blueprint, jsonify, request

from ..errors import ValidationError
from ..repositories import AuditRepository, RuleRepository
from ..validators import validate_rule_payload

rules_bp = Blueprint("rules", __name__, url_prefix="/api/v1/rules")


def _repo() -> RuleRepository:
    return RuleRepository()


def _audit() -> AuditRepository:
    return AuditRepository()


@rules_bp.get("")
def list_rules():
    enabled_param = request.args.get("enabled")
    enabled = None
    if enabled_param is not None:
        enabled = enabled_param.lower() in ("1", "true", "yes")
    rules = _repo().list(enabled=enabled)
    return jsonify({"items": rules, "total": len(rules)})


@rules_bp.post("")
def create_rule():
    payload = request.get_json(silent=True) or {}
    data = validate_rule_payload(payload)
    rule = _repo().create(data)
    _audit().record(
        event_type="rule_created",
        entity_type="rule",
        entity_id=rule["id"],
        detail={"rule_name": rule["rule_name"]},
    )
    return jsonify(rule), 201


@rules_bp.get("/<int:rule_id>")
def get_rule(rule_id: int):
    return jsonify(_repo().get_by_id(rule_id))


@rules_bp.put("/<int:rule_id>")
def update_rule(rule_id: int):
    existing = _repo().get_by_id(rule_id)
    payload = request.get_json(silent=True) or {}
    merged = {**existing, **payload}
    data = validate_rule_payload(merged)
    rule = _repo().update(rule_id, data)
    _audit().record(
        event_type="rule_updated",
        entity_type="rule",
        entity_id=rule["id"],
        detail={"fields": list(payload.keys())},
    )
    return jsonify(rule)


@rules_bp.post("/<int:rule_id>/enable")
def enable_rule(rule_id: int):
    rule = _repo().set_enabled(rule_id, True)
    _audit().record(
        event_type="rule_enabled", entity_type="rule", entity_id=rule_id
    )
    return jsonify(rule)


@rules_bp.post("/<int:rule_id>/disable")
def disable_rule(rule_id: int):
    rule = _repo().set_enabled(rule_id, False)
    _audit().record(
        event_type="rule_disabled", entity_type="rule", entity_id=rule_id
    )
    return jsonify(rule)


@rules_bp.post("/<int:rule_id>/priority")
def set_priority(rule_id: int):
    payload = request.get_json(silent=True) or {}
    priority = payload.get("priority")
    if not isinstance(priority, int) or priority < 0:
        raise ValidationError(
            "priority 必须是非负整数", details={"field": "priority"}
        )
    rule = _repo().set_priority(rule_id, priority)
    _audit().record(
        event_type="rule_priority_changed",
        entity_type="rule",
        entity_id=rule_id,
        detail={"priority": priority},
    )
    return jsonify(rule)


@rules_bp.delete("/<int:rule_id>")
def delete_rule(rule_id: int):
    _repo().delete(rule_id)
    _audit().record(
        event_type="rule_deleted", entity_type="rule", entity_id=rule_id
    )
    return jsonify({"deleted": True, "rule_id": rule_id})
