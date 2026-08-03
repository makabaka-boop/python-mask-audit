from __future__ import annotations
"""脱敏预览接口（不写入演练记录）。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.audit import AuditHelper
from app.core.errors import NotFoundError, RuleDisabledError
from app.database import get_db
from app.repositories.rule_repo import RuleRepository
from app.repositories.sample_repo import SampleRepository
from app.schemas.rule import RulePreviewRequest
from app.services.executor import RuleExecutor

router = APIRouter()


@router.post("")
def preview_masking(payload: RulePreviewRequest, db: Session = Depends(get_db)):
    rule = RuleRepository.get_by_id(db, payload.rule_id)
    if rule is None:
        raise NotFoundError(f"规则 {payload.rule_id} 不存在")
    if not rule.enabled:
        raise RuleDisabledError(f"规则 {payload.rule_id} 已禁用，无法预览")

    if payload.input_text is not None and payload.input_text != "":
        input_text = payload.input_text
    elif payload.sample_id is not None:
        sample = SampleRepository.get_by_id(db, payload.sample_id)
        if sample is None:
            raise NotFoundError(f"样例 {payload.sample_id} 不存在")
        input_text = sample.raw_text
    else:
        from app.core.errors import ValidationError
        raise ValidationError("必须提供 sample_id 或 input_text")

    result = RuleExecutor.execute_single(input_text, rule.to_dict())

    AuditHelper.log_event(db, AuditHelper.PREVIEW, "rule", rule.id,
                          {"hit_count": result["hit_count"]})

    return {
        "rule_id": rule.id,
        "rule_name": rule.rule_name,
        "input_text": input_text,
        "output_text": result["output_text"],
        "hit_count": result["hit_count"],
        "hit_details": result["hit_details"],
    }
