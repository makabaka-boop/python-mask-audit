from __future__ import annotations
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import AuditEvent


class AuditRepository:

    @staticmethod
    def log(
        db: Session,
        event_type: str,
        target_type: str = "",
        target_id: int | None = None,
        detail=None,
    ) -> AuditEvent:
        if detail is None:
            detail_str = "{}"
        elif isinstance(detail, str):
            detail_str = detail
        else:
            detail_str = json.dumps(detail, ensure_ascii=False)

        event = AuditEvent(
            event_type=event_type,
            target_type=target_type or "",
            target_id=target_id,
            detail=detail_str,
            created_at=datetime.utcnow(),
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    @staticmethod
    def list_events(
        db: Session,
        event_type: str | None = None,
        target_type: str | None = None,
        target_id: int | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        query = db.query(AuditEvent)
        if event_type is not None:
            query = query.filter(AuditEvent.event_type == event_type)
        if target_type is not None:
            query = query.filter(AuditEvent.target_type == target_type)
        if target_id is not None:
            query = query.filter(AuditEvent.target_id == target_id)
        return (
            query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_latest_event(
        db: Session,
        event_type: str | None = None,
        target_type: str | None = None,
        target_id: int | None = None,
    ) -> AuditEvent | None:
        query = db.query(AuditEvent)
        if event_type is not None:
            query = query.filter(AuditEvent.event_type == event_type)
        if target_type is not None:
            query = query.filter(AuditEvent.target_type == target_type)
        if target_id is not None:
            query = query.filter(AuditEvent.target_id == target_id)
        return (
            query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .first()
        )
