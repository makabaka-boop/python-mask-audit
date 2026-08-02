"""规则分组仓储。"""
from __future__ import annotations

from typing import Any, Dict, List

from ..database import db_cursor
from ..errors import ConflictError, NotFoundError, RuleDisabledError
from .base import row_to_dict, rows_to_list


class GroupRepository:
    def create(self, group_name: str, description: str = None) -> Dict[str, Any]:
        try:
            with db_cursor(commit=True) as cur:
                cur.execute(
                    "INSERT INTO groups (group_name, description) VALUES (?, ?)",
                    (group_name, description),
                )
                group_id = cur.lastrowid
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise ConflictError(
                    f"分组 {group_name} 已存在", details={"group_name": group_name}
                )
            raise
        return self.get_by_id(group_id)

    def get_by_id(self, group_id: int) -> Dict[str, Any]:
        with db_cursor() as cur:
            cur.execute("SELECT * FROM groups WHERE id = ?", (group_id,))
            row = cur.fetchone()
        if row is None:
            raise NotFoundError(
                f"分组 {group_id} 不存在", details={"group_id": group_id}
            )
        return row_to_dict(row)

    def list(self) -> List[Dict[str, Any]]:
        with db_cursor() as cur:
            cur.execute("SELECT * FROM groups ORDER BY id ASC")
            rows = cur.fetchall()
        return rows_to_list(rows)

    def add_rule(self, group_id: int, rule_id: int) -> None:
        self.get_by_id(group_id)
        with db_cursor() as cur:
            cur.execute("SELECT enabled FROM rules WHERE id = ?", (rule_id,))
            row = cur.fetchone()
            if row is None:
                raise NotFoundError(
                    f"规则 {rule_id} 不存在", details={"rule_id": rule_id}
                )
            if not row["enabled"]:
                raise RuleDisabledError(
                    f"规则 {rule_id} 已禁用，不能加入分组",
                    details={"rule_id": rule_id, "group_id": group_id},
                )
            cur.execute(
                "INSERT OR IGNORE INTO group_members (group_id, rule_id) VALUES (?, ?)",
                (group_id, rule_id),
            )
        cur.connection.commit()

    def remove_rule(self, group_id: int, rule_id: int) -> None:
        self.get_by_id(group_id)
        with db_cursor(commit=True) as cur:
            cur.execute(
                "DELETE FROM group_members WHERE group_id = ? AND rule_id = ?",
                (group_id, rule_id),
            )

    def list_rules(self, group_id: int, only_enabled: bool = False) -> List[Dict[str, Any]]:
        self.get_by_id(group_id)
        sql = (
            "SELECT r.* FROM rules r "
            "INNER JOIN group_members gm ON gm.rule_id = r.id WHERE gm.group_id = ?"
        )
        if only_enabled:
            sql += " AND r.enabled = 1"
        sql += " ORDER BY r.priority ASC, r.id ASC"
        with db_cursor() as cur:
            cur.execute(sql, (group_id,))
            rows = cur.fetchall()
        from .rule_repo import RuleRepository

        return [RuleRepository._normalize(row_to_dict(r)) for r in rows]

    def delete(self, group_id: int) -> None:
        self.get_by_id(group_id)
        with db_cursor(commit=True) as cur:
            cur.execute("DELETE FROM groups WHERE id = ?", (group_id,))
