from __future__ import annotations
"""规则快照模型。"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey

from app.database import Base


class RuleSnapshot(Base):
    __tablename__ = "rule_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("rule_groups.id", ondelete="SET NULL"),
                      nullable=True)
    label = Column(String(200), nullable=True, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "group_id": self.group_id,
            "label": self.label or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SnapshotItem(Base):
    __tablename__ = "snapshot_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(Integer, ForeignKey("rule_snapshots.id", ondelete="CASCADE"),
                         nullable=False)
    rule_id = Column(Integer, nullable=False)
    rule_name = Column(String(200), nullable=False)
    enabled = Column(Integer, nullable=False, default=1)
    priority = Column(Integer, nullable=False, default=100)
    match_type = Column(String(20), nullable=False)
    match_value = Column(Text, nullable=False)
    replace_strategy = Column(String(20), nullable=False)
    replace_config = Column(Text, nullable=False, default="{}")

    def to_dict(self) -> dict:
        import json
        return {
            "id": self.id,
            "snapshot_id": self.snapshot_id,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "enabled": bool(self.enabled),
            "priority": self.priority,
            "match_type": self.match_type,
            "match_value": self.match_value,
            "replace_strategy": self.replace_strategy,
            "replace_config": json.loads(self.replace_config) if self.replace_config else {},
        }
