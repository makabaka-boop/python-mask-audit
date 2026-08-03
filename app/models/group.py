from __future__ import annotations
"""分组模型。"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint

from app.database import Base


class RuleGroup(Base):
    __tablename__ = "rule_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_name = Column(String(200), nullable=False, unique=True)
    description = Column(String(500), nullable=True, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "group_name": self.group_name,
            "description": self.description or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "rule_id", name="uq_group_rule"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("rule_groups.id", ondelete="CASCADE"),
                      nullable=False)
    rule_id = Column(Integer, ForeignKey("rules.id", ondelete="CASCADE"),
                     nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "group_id": self.group_id,
            "rule_id": self.rule_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
