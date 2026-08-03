from __future__ import annotations
"""规则冲突检测接口。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.audit import AuditHelper
from app.core.conflict import ConflictDetector
from app.core.errors import NotFoundError
from app.database import get_db
from app.repositories.group_repo import GroupRepository
from app.schemas.conflict import ConflictItem, ConflictResponse

router = APIRouter()


@router.get("/groups/{group_id}", response_model=ConflictResponse)
def detect_group_conflicts(group_id: int, db: Session = Depends(get_db)):
    group = GroupRepository.get_by_id(db, group_id)
    if group is None:
        raise NotFoundError(f"分组 {group_id} 不存在")

    rules = GroupRepository.get_rules(db, group_id, enabled_only=False)
    rule_dicts = [r.to_dict() for r in rules]

    conflicts = ConflictDetector.detect(rule_dicts)

    AuditHelper.log_event(db, AuditHelper.CONFLICT_DETECT, "group", group_id,
                          {"total_conflicts": len(conflicts)})

    return ConflictResponse(
        group_id=group_id,
        total=len(conflicts),
        conflicts=[ConflictItem(**c) for c in conflicts],
    )
