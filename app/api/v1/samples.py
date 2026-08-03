from __future__ import annotations
"""样例文本管理接口。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.audit import AuditHelper
from app.core.errors import NotFoundError, ValidationError
from app.database import get_db
from app.repositories.sample_repo import SampleRepository
from app.schemas.sample import SampleCreate, SampleUpdate, SampleResponse

router = APIRouter()


@router.post("", response_model=SampleResponse, status_code=201)
def create_sample(payload: SampleCreate, db: Session = Depends(get_db)):
    sample = SampleRepository.create(db, **payload.model_dump())
    AuditHelper.log_event(db, AuditHelper.SAMPLE_CREATE, "sample", sample.id,
                          {"sample_name": sample.sample_name})
    return SampleResponse.model_validate(sample.to_dict())


@router.get("", response_model=list[SampleResponse])
def list_samples(category: str | None = None, db: Session = Depends(get_db)):
    samples = SampleRepository.list_all(db, category=category)
    return [SampleResponse.model_validate(s.to_dict()) for s in samples]


@router.get("/{sample_id}", response_model=SampleResponse)
def get_sample(sample_id: int, db: Session = Depends(get_db)):
    sample = SampleRepository.get_by_id(db, sample_id)
    if sample is None:
        raise NotFoundError(f"样例 {sample_id} 不存在")
    return SampleResponse.model_validate(sample.to_dict())


@router.put("/{sample_id}", response_model=SampleResponse)
def update_sample(sample_id: int, payload: SampleUpdate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise ValidationError("未提供更新字段")
    sample = SampleRepository.update(db, sample_id, **data)
    if sample is None:
        raise NotFoundError(f"样例 {sample_id} 不存在")
    AuditHelper.log_event(db, AuditHelper.SAMPLE_UPDATE, "sample", sample.id,
                          {"updated_fields": list(data.keys())})
    return SampleResponse.model_validate(sample.to_dict())


@router.delete("/{sample_id}", status_code=204)
def delete_sample(sample_id: int, db: Session = Depends(get_db)):
    ok = SampleRepository.delete(db, sample_id)
    if not ok:
        raise NotFoundError(f"样例 {sample_id} 不存在")
    AuditHelper.log_event(db, AuditHelper.SAMPLE_DELETE, "sample", sample_id,
                          {"action": "deleted"})
