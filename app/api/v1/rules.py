from __future__ import annotations
"""规则管理接口。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.audit import AuditHelper
from app.core.errors import NotFoundError, ValidationError
from app.database import get_db
from app.repositories.rule_repo import RuleRepository
from app.schemas.rule import (
    RuleCreate,
    RuleUpdate,
    RuleResponse,
    RuleToggle,
    RulePriorityUpdate,
)

router = APIRouter()


@router.post("", response_model=RuleResponse, status_code=201)
def create_rule(payload: RuleCreate, db: Session = Depends(get_db)):
    try:
        rule = RuleRepository.create(db, **payload.model_dump())
    except ValueError as exc:
        raise ValidationError(str(exc))
    AuditHelper.log_event(db, AuditHelper.RULE_CREATE, "rule", rule.id,
                          {"rule_name": rule.rule_name})
    return RuleResponse.model_validate(rule.to_dict())


@router.get("", response_model=list[RuleResponse])
def list_rules(enabled_only: bool = False, db: Session = Depends(get_db)):
    rules = RuleRepository.list_all(db, enabled_only=enabled_only)
    return [RuleResponse.model_validate(r.to_dict()) for r in rules]


@router.get("/{rule_id}", response_model=RuleResponse)
def get_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = RuleRepository.get_by_id(db, rule_id)
    if rule is None:
        raise NotFoundError(f"规则 {rule_id} 不存在")
    return RuleResponse.model_validate(rule.to_dict())


@router.put("/{rule_id}", response_model=RuleResponse)
def update_rule(rule_id: int, payload: RuleUpdate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise ValidationError("未提供更新字段")
    try:
        rule = RuleRepository.update(db, rule_id, **data)
    except ValueError as exc:
        raise ValidationError(str(exc))
    if rule is None:
        raise NotFoundError(f"规则 {rule_id} 不存在")
    AuditHelper.log_event(db, AuditHelper.RULE_UPDATE, "rule", rule.id,
                          {"updated_fields": list(data.keys())})
    return RuleResponse.model_validate(rule.to_dict())


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    ok = RuleRepository.delete(db, rule_id)
    if not ok:
        raise NotFoundError(f"规则 {rule_id} 不存在")
    AuditHelper.log_event(db, AuditHelper.RULE_UPDATE, "rule", rule_id,
                          {"action": "deleted"})


@router.patch("/{rule_id}/enabled", response_model=RuleResponse)
def toggle_rule(rule_id: int, payload: RuleToggle, db: Session = Depends(get_db)):
    rule = RuleRepository.set_enabled(db, rule_id, payload.enabled)
    if rule is None:
        raise NotFoundError(f"规则 {rule_id} 不存在")
    event_type = AuditHelper.RULE_ENABLE if payload.enabled else AuditHelper.RULE_DISABLE
    AuditHelper.log_event(db, event_type, "rule", rule.id, {"enabled": payload.enabled})
    return RuleResponse.model_validate(rule.to_dict())


@router.patch("/{rule_id}/priority", response_model=RuleResponse)
def update_priority(rule_id: int, payload: RulePriorityUpdate,
                    db: Session = Depends(get_db)):
    rule = RuleRepository.set_priority(db, rule_id, payload.priority)
    if rule is None:
        raise NotFoundError(f"规则 {rule_id} 不存在")
    AuditHelper.log_event(db, AuditHelper.RULE_PRIORITY, "rule", rule.id,
                          {"priority": payload.priority})
    return RuleResponse.model_validate(rule.to_dict())
