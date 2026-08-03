from __future__ import annotations
from sqlalchemy.orm import Session

from app.models import SampleText


class SampleRepository:

    @staticmethod
    def create(
        db: Session,
        sample_name: str,
        raw_text: str,
        sample_category: str = "general",
        expected_note: str = "",
    ) -> SampleText:
        sample = SampleText(
            sample_name=sample_name,
            raw_text=raw_text,
            sample_category=sample_category or "general",
            expected_note=expected_note or "",
        )
        db.add(sample)
        db.commit()
        db.refresh(sample)
        return sample

    @staticmethod
    def get_by_id(db: Session, sample_id: int) -> SampleText | None:
        return db.query(SampleText).filter(SampleText.id == sample_id).first()

    @staticmethod
    def list_all(db: Session, category: str | None = None) -> list[SampleText]:
        query = db.query(SampleText)
        if category is not None:
            query = query.filter(SampleText.sample_category == category)
        return query.order_by(SampleText.id.asc()).all()

    @staticmethod
    def update(db: Session, sample_id: int, **kwargs) -> SampleText | None:
        sample = db.query(SampleText).filter(SampleText.id == sample_id).first()
        if sample is None:
            return None
        for key, value in kwargs.items():
            setattr(sample, key, value)
        db.commit()
        db.refresh(sample)
        return sample

    @staticmethod
    def delete(db: Session, sample_id: int) -> bool:
        sample = db.query(SampleText).filter(SampleText.id == sample_id).first()
        if sample is None:
            return False
        db.delete(sample)
        db.commit()
        return True
