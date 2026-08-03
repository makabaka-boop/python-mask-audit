"""规则快照仓储。"""
from __future__ import annotations

from typing import Any, Dict, List

from ..database import db_cursor
from ..errors import NotFoundError
from .base import dumps_json, parse_json_field, row_to_dict, rows_to_list


class SnapshotRepository:
    def create_for_run(
        self, run_id: int, rules: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        created: List[Dict[str, Any]] = []
        with db_cursor(commit=True) as cur:
            for rule in rules:
                cur.execute(
                    """
                    INSERT INTO rule_snapshots (
                        run_id, rule_id, rule_name, enabled, priority,
                        match_type, match_value, replace_strategy, replace_config
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        rule.get("id"),
                        rule.get("rule_name"),
                        1 if rule.get("enabled") else 0,
                        rule.get("priority"),
                        rule.get("match_type"),
                        rule.get("match_value"),
                        rule.get("replace_strategy"),
                        dumps_json(rule.get("replace_config") or {}),
                    ),
                )
                snap_id = cur.lastrowid
                cur.execute("SELECT * FROM rule_snapshots WHERE id = ?", (snap_id,))
                created.append(self._normalize(row_to_dict(cur.fetchone())))
        return created

    def list_by_run(self, run_id: int) -> List[Dict[str, Any]]:
        with db_cursor() as cur:
            cur.execute(
                "SELECT * FROM rule_snapshots WHERE run_id = ? ORDER BY priority ASC, id ASC",
                (run_id,),
            )
            rows = cur.fetchall()
        if not rows:
            raise NotFoundError(
                f"演练 {run_id} 没有规则快照", details={"run_id": run_id}
            )
        return [self._normalize(row_to_dict(r)) for r in rows]

    @staticmethod
    def _normalize(snap: Dict[str, Any]) -> Dict[str, Any]:
        snap["replace_config"] = parse_json_field(snap.get("replace_config"), {})
        snap["enabled"] = bool(snap.get("enabled"))
        return snap
