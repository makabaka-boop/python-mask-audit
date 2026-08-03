from __future__ import annotations
"""审计查询接口：从规则、样例、分组三个维度追踪演练历史。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.repositories.audit_repo import AuditRepository
from app.schemas.audit_view import (
    GroupAuditView,
    RuleAuditView,
    SampleAuditView,
)
from app.services.audit_query import AuditQueryService

router = APIRouter()


@router.get("/rules/{rule_id}", response_model=RuleAuditView)
def rule_audit_view(rule_id: int, db: Session = Depends(get_db)):
    result = AuditQueryService.rule_view(db, rule_id)
    if result is None:
        raise NotFoundError(f"规则 {rule_id} 不存在")
    return RuleAuditView.model_validate(result)


@router.get("/samples/{sample_id}", response_model=SampleAuditView)
def sample_audit_view(sample_id: int, db: Session = Depends(get_db)):
    result = AuditQueryService.sample_view(db, sample_id)
    if result is None:
        raise NotFoundError(f"样例 {sample_id} 不存在")
    return SampleAuditView.model_validate(result)


@router.get("/groups/{group_id}", response_model=GroupAuditView)
def group_audit_view(group_id: int, db: Session = Depends(get_db)):
    result = AuditQueryService.group_view(db, group_id)
    if result is None:
        raise NotFoundError(f"分组 {group_id} 不存在")
    return GroupAuditView.model_validate(result)


@router.get("/events")
def list_audit_events(
    event_type: str | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    events = AuditRepository.list_events(
        db,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        limit=limit,
    )
    return [e.to_dict() for e in events]
