from __future__ import annotations
"""分组管理接口。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.audit import AuditHelper
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.database import get_db
from app.repositories.group_repo import GroupRepository
from app.repositories.rule_repo import RuleRepository
from app.schemas.group import (
    GroupCreate,
    GroupUpdate,
    GroupResponse,
    GroupMemberRequest,
    GroupMemberResponse,
    GroupWithRules,
)
from app.schemas.rule import RuleResponse

router = APIRouter()


@router.post("", response_model=GroupResponse, status_code=201)
def create_group(payload: GroupCreate, db: Session = Depends(get_db)):
    group = GroupRepository.create(db, group_name=payload.group_name,
                                   description=payload.description)
    AuditHelper.log_event(db, AuditHelper.GROUP_CREATE, "group", group.id,
                          {"group_name": group.group_name})
    return GroupResponse.model_validate(group.to_dict())


@router.get("", response_model=list[GroupResponse])
def list_groups(db: Session = Depends(get_db)):
    groups = GroupRepository.list_all(db)
    return [GroupResponse.model_validate(g.to_dict()) for g in groups]


@router.get("/{group_id}", response_model=GroupWithRules)
def get_group(group_id: int, db: Session = Depends(get_db)):
    group = GroupRepository.get_by_id(db, group_id)
    if group is None:
        raise NotFoundError(f"分组 {group_id} 不存在")
    rules = GroupRepository.get_rules(db, group_id)
    result = group.to_dict()
    result["rules"] = [RuleResponse.model_validate(r.to_dict()) for r in rules]
    return GroupWithRules.model_validate(result)


@router.put("/{group_id}", response_model=GroupResponse)
def update_group(group_id: int, payload: GroupUpdate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise ValidationError("未提供更新字段")
    group = GroupRepository.update(db, group_id, **data)
    if group is None:
        raise NotFoundError(f"分组 {group_id} 不存在")
    AuditHelper.log_event(db, AuditHelper.GROUP_UPDATE, "group", group.id,
                          {"updated_fields": list(data.keys())})
    return GroupResponse.model_validate(group.to_dict())


@router.delete("/{group_id}", status_code=204)
def delete_group(group_id: int, db: Session = Depends(get_db)):
    ok = GroupRepository.delete(db, group_id)
    if not ok:
        raise NotFoundError(f"分组 {group_id} 不存在")
    AuditHelper.log_event(db, AuditHelper.GROUP_DELETE, "group", group_id,
                          {"action": "deleted"})


@router.post("/{group_id}/rules", response_model=GroupMemberResponse, status_code=201)
def add_rule_to_group(group_id: int, payload: GroupMemberRequest,
                      db: Session = Depends(get_db)):
    group = GroupRepository.get_by_id(db, group_id)
    if group is None:
        raise NotFoundError(f"分组 {group_id} 不存在")
    rule = RuleRepository.get_by_id(db, payload.rule_id)
    if rule is None:
        raise NotFoundError(f"规则 {payload.rule_id} 不存在")
    try:
        member = GroupRepository.add_rule(db, group_id, payload.rule_id)
    except ValueError as exc:
        raise ConflictError(str(exc))
    AuditHelper.log_event(db, AuditHelper.GROUP_ADD_RULE, "group", group_id,
                          {"rule_id": payload.rule_id})
    return GroupMemberResponse.model_validate(member.to_dict())


@router.delete("/{group_id}/rules/{rule_id}", status_code=204)
def remove_rule_from_group(group_id: int, rule_id: int, db: Session = Depends(get_db)):
    ok = GroupRepository.remove_rule(db, group_id, rule_id)
    if not ok:
        raise NotFoundError(f"分组 {group_id} 中不存在规则 {rule_id}")
    AuditHelper.log_event(db, AuditHelper.GROUP_REMOVE_RULE, "group", group_id,
                          {"rule_id": rule_id})


@router.get("/{group_id}/rules", response_model=list[RuleResponse])
def list_group_rules(group_id: int, enabled_only: bool = False,
                     db: Session = Depends(get_db)):
    group = GroupRepository.get_by_id(db, group_id)
    if group is None:
        raise NotFoundError(f"分组 {group_id} 不存在")
    rules = GroupRepository.get_rules(db, group_id, enabled_only=enabled_only)
    return [RuleResponse.model_validate(r.to_dict()) for r in rules]
