from __future__ import annotations
"""演练记录与命中明细模型。"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey

from app.database import Base


class RunRecord(Base):
    __tablename__ = "run_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sample_id = Column(Integer, ForeignKey("sample_texts.id", ondelete="SET NULL"),
                       nullable=True)
    rule_id = Column(Integer, ForeignKey("rules.id", ondelete="SET NULL"),
                     nullable=True)
    group_id = Column(Integer, ForeignKey("rule_groups.id", ondelete="SET NULL"),
                      nullable=True)
    input_text = Column(Text, nullable=False)
    output_text = Column(Text, nullable=False)
    hit_count = Column(Integer, nullable=False, default=0)
    snapshot_id = Column(Integer, ForeignKey("rule_snapshots.id", ondelete="SET NULL"),
                         nullable=True)
    executed_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sample_id": self.sample_id,
            "rule_id": self.rule_id,
            "group_id": self.group_id,
            "input_text": self.input_text,
            "output_text": self.output_text,
            "hit_count": self.hit_count,
            "snapshot_id": self.snapshot_id,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }


class HitDetail(Base):
    __tablename__ = "hit_details"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("run_records.id", ondelete="CASCADE"),
                    nullable=False)
    rule_id = Column(Integer, ForeignKey("rules.id", ondelete="SET NULL"),
                     nullable=True)
    matched_count = Column(Integer, nullable=False, default=0)
    before_fragment = Column(Text, nullable=False, default="")
    after_fragment = Column(Text, nullable=False, default="")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "rule_id": self.rule_id,
            "matched_count": self.matched_count,
            "before_fragment": self.before_fragment,
            "after_fragment": self.after_fragment,
        }
