"""审计事件仓储。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..database import db_cursor
from .base import dumps_json, row_to_dict, rows_to_list


class AuditRepository:
    def record(
        self,
        event_type: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO audit_events (event_type, entity_type, entity_id, detail)
                VALUES (?, ?, ?, ?)
                """,
                (event_type, entity_type, entity_id, dumps_json(detail or {})),
            )
            event_id = cur.lastrowid
            cur.execute("SELECT * FROM audit_events WHERE id = ?", (event_id,))
            row = cur.fetchone()
        return row_to_dict(row)

    def list(self, limit: int = 100) -> List[Dict[str, Any]]:
        with db_cursor() as cur:
            cur.execute(
                "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)
            )
            rows = cur.fetchall()
        return rows_to_list(rows)

    def list_by_entity(
        self, entity_type: str, entity_id: int, limit: int = 20
    ) -> List[Dict[str, Any]]:
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT * FROM audit_events
                WHERE entity_type = ? AND entity_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (entity_type, entity_id, limit),
            )
            rows = cur.fetchall()
        return rows_to_list(rows)
