"""规则分组路由。"""
from flask import Blueprint, jsonify, request

from ..conflict_detector import detect_conflicts
from ..errors import ValidationError
from ..repositories import AuditRepository, GroupRepository

groups_bp = Blueprint("groups", __name__, url_prefix="/api/v1/groups")


def _repo() -> GroupRepository:
    return GroupRepository()


def _audit() -> AuditRepository:
    return AuditRepository()


@groups_bp.get("")
def list_groups():
    groups = _repo().list()
    return jsonify({"items": groups, "total": len(groups)})


@groups_bp.post("")
def create_group():
    payload = request.get_json(silent=True) or {}
    group_name = payload.get("group_name")
    if not group_name or not isinstance(group_name, str):
        raise ValidationError(
            "group_name 不能为空", details={"field": "group_name"}
        )
    description = payload.get("description")
    group = _repo().create(group_name, description)
    _audit().record(
        event_type="group_created",
        entity_type="group",
        entity_id=group["id"],
        detail={"group_name": group_name},
    )
    return jsonify(group), 201


@groups_bp.get("/<int:group_id>")
def get_group(group_id: int):
    group = _repo().get_by_id(group_id)
    rules = _repo().list_rules(group_id)
    return jsonify({**group, "rules": rules, "rule_count": len(rules)})


@groups_bp.post("/<int:group_id>/rules")
def add_rule(group_id: int):
    payload = request.get_json(silent=True) or {}
    rule_id = payload.get("rule_id")
    if not isinstance(rule_id, int):
        raise ValidationError(
            "rule_id 必须是整数", details={"field": "rule_id"}
        )
    _repo().add_rule(group_id, rule_id)
    _audit().record(
        event_type="group_rule_added",
        entity_type="group",
        entity_id=group_id,
        detail={"rule_id": rule_id},
    )
    return jsonify({"group_id": group_id, "rule_id": rule_id, "added": True})


@groups_bp.delete("/<int:group_id>/rules/<int:rule_id>")
def remove_rule(group_id: int, rule_id: int):
    _repo().remove_rule(group_id, rule_id)
    _audit().record(
        event_type="group_rule_removed",
        entity_type="group",
        entity_id=group_id,
        detail={"rule_id": rule_id},
    )
    return jsonify({"group_id": group_id, "rule_id": rule_id, "removed": True})


@groups_bp.get("/<int:group_id>/rules")
def list_group_rules(group_id: int):
    rules = _repo().list_rules(group_id)
    return jsonify({"items": rules, "total": len(rules)})


@groups_bp.get("/<int:group_id>/conflicts")
def group_conflicts(group_id: int):
    """对分组内的规则进行冲突检测，只返回风险提示，不阻断任何操作。"""
    include_disabled = request.args.get("include_disabled", "0") == "1"
    repo = _repo()
    repo.get_by_id(group_id)
    rules = repo.list_rules(group_id, only_enabled=not include_disabled)
    conflicts = detect_conflicts(rules)
    return jsonify(
        {
            "group_id": group_id,
            "rule_count": len(rules),
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
        }
    )


@groups_bp.delete("/<int:group_id>")
def delete_group(group_id: int):
    _repo().delete(group_id)
    _audit().record(
        event_type="group_deleted", entity_type="group", entity_id=group_id
    )
    return jsonify({"deleted": True, "group_id": group_id})
