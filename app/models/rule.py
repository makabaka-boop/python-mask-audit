from __future__ import annotations
"""规则模型。"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text

from app.database import Base


class Rule(Base):
    __tablename__ = "rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_name = Column(String(200), nullable=False)
    field_type = Column(String(100), nullable=False, default="text")
    match_type = Column(String(20), nullable=False)  # exact, contains, regex
    match_value = Column(Text, nullable=False)
    replace_strategy = Column(String(20), nullable=False)  # fixed, keep_edges, middle_mask
    replace_config = Column(Text, nullable=False, default="{}")  # JSON string
    priority = Column(Integer, nullable=False, default=100)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        import json
        return {
            "id": self.id,
            "rule_name": self.rule_name,
            "field_type": self.field_type,
            "match_type": self.match_type,
            "match_value": self.match_value,
            "replace_strategy": self.replace_strategy,
            "replace_config": json.loads(self.replace_config) if self.replace_config else {},
            "priority": self.priority,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
