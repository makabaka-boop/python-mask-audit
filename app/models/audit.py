from __future__ import annotations
"""审计事件模型。"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text

from app.database import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False)
    target_type = Column(String(50), nullable=False, default="")
    target_id = Column(Integer, nullable=True)
    detail = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        import json
        return {
            "id": self.id,
            "event_type": self.event_type,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "detail": json.loads(self.detail) if self.detail else {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
