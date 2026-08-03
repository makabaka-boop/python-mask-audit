from __future__ import annotations
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import RuleSnapshot, SnapshotItem


class SnapshotRepository:

    @staticmethod
    def create(db: Session, group_id: int | None = None, label: str = "") -> RuleSnapshot:
        snapshot = RuleSnapshot(
            group_id=group_id,
            label=label or "",
            created_at=datetime.utcnow(),
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
        return snapshot

    @staticmethod
    def add_item(
        db: Session,
        snapshot_id: int,
        rule_id: int,
        rule_name: str,
        enabled: int,
        priority: int,
        match_type: str,
        match_value: str,
        replace_strategy: str,
        replace_config,
    ) -> SnapshotItem:
        if not isinstance(replace_config, str):
            replace_config = json.dumps(replace_config, ensure_ascii=False)
        item = SnapshotItem(
            snapshot_id=snapshot_id,
            rule_id=rule_id,
            rule_name=rule_name,
            enabled=enabled,
            priority=priority,
            match_type=match_type,
            match_value=match_value,
            replace_strategy=replace_strategy,
            replace_config=replace_config or "{}",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def get_by_id(db: Session, snapshot_id: int) -> RuleSnapshot | None:
        return db.query(RuleSnapshot).filter(RuleSnapshot.id == snapshot_id).first()

    @staticmethod
    def get_items(db: Session, snapshot_id: int) -> list[SnapshotItem]:
        return (
            db.query(SnapshotItem)
            .filter(SnapshotItem.snapshot_id == snapshot_id)
            .order_by(SnapshotItem.priority.asc(), SnapshotItem.id.asc())
            .all()
        )

    @staticmethod
    def get_latest_by_group(db: Session, group_id: int) -> RuleSnapshot | None:
        return (
            db.query(RuleSnapshot)
            .filter(RuleSnapshot.group_id == group_id)
            .order_by(RuleSnapshot.created_at.desc(), RuleSnapshot.id.desc())
            .first()
        )

    @staticmethod
    def list_by_group(db: Session, group_id: int, limit: int = 20) -> list[RuleSnapshot]:
        return (
            db.query(RuleSnapshot)
            .filter(RuleSnapshot.group_id == group_id)
            .order_by(RuleSnapshot.created_at.desc(), RuleSnapshot.id.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_items_by_rule(db: Session, rule_id: int) -> list[SnapshotItem]:
        return (
            db.query(SnapshotItem)
            .filter(SnapshotItem.rule_id == rule_id)
            .order_by(SnapshotItem.id.desc())
            .all()
        )

    @staticmethod
    def get_snapshots_by_group(db: Session, group_id: int,
                               limit: int = 20) -> list[RuleSnapshot]:
        return (
            db.query(RuleSnapshot)
            .filter(RuleSnapshot.group_id == group_id)
            .order_by(RuleSnapshot.created_at.desc(), RuleSnapshot.id.desc())
            .limit(limit)
            .all()
        )
