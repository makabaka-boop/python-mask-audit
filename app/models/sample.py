from __future__ import annotations
"""样例文本模型。"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text

from app.database import Base


class SampleText(Base):
    __tablename__ = "sample_texts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sample_name = Column(String(200), nullable=False)
    sample_category = Column(String(100), nullable=False, default="general")
    raw_text = Column(Text, nullable=False)
    expected_note = Column(String(500), nullable=True, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sample_name": self.sample_name,
            "sample_category": self.sample_category,
            "raw_text": self.raw_text,
            "expected_note": self.expected_note or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
