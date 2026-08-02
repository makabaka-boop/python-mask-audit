"""规则仓储。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..database import db_cursor
from ..errors import ConflictError, NotFoundError
from .base import dumps_json, parse_json_field, row_to_dict, rows_to_list


class RuleRepository:
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO rules (
                    rule_name, field_type, match_type, match_value,
                    replace_strategy, replace_config, priority, enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["rule_name"],
                    data["field_type"],
                    data["match_type"],
                    data["match_value"],
                    data["replace_strategy"],
                    dumps_json(data["replace_config"]),
                    data["priority"],
                    1 if data["enabled"] else 0,
                ),
            )
            rule_id = cur.lastrowid
        return self.get_by_id(rule_id)

    def get_by_id(self, rule_id: int) -> Dict[str, Any]:
        with db_cursor() as cur:
            cur.execute("SELECT * FROM rules WHERE id = ?", (rule_id,))
            row = cur.fetchone()
        if row is None:
            raise NotFoundError(f"规则 {rule_id} 不存在", details={"rule_id": rule_id})
        return self._normalize(row_to_dict(row))

    def list(self, enabled: Optional[bool] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM rules"
        params: list = []
        if enabled is not None:
            sql += " WHERE enabled = ?"
            params.append(1 if enabled else 0)
        sql += " ORDER BY priority ASC, id ASC"
        with db_cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [self._normalize(row_to_dict(r)) for r in rows]

    def update(self, rule_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        self.get_by_id(rule_id)
        fields = []
        params: list = []
        mapping = {
            "rule_name": "rule_name",
            "field_type": "field_type",
            "match_type": "match_type",
            "match_value": "match_value",
            "replace_strategy": "replace_strategy",
            "priority": "priority",
            "enabled": "enabled",
        }
        for key, column in mapping.items():
            if key in data:
                fields.append(f"{column} = ?")
                value = data[key]
                if key == "enabled":
                    value = 1 if value else 0
                params.append(value)
        if "replace_config" in data:
            fields.append("replace_config = ?")
            params.append(dumps_json(data["replace_config"]))

        if not fields:
            return self.get_by_id(rule_id)

        fields.append("updated_at = datetime('now')")
        params.append(rule_id)
        with db_cursor(commit=True) as cur:
            cur.execute(
                f"UPDATE rules SET {', '.join(fields)} WHERE id = ?", params
            )
        return self.get_by_id(rule_id)

    def set_enabled(self, rule_id: int, enabled: bool) -> Dict[str, Any]:
        return self.update(rule_id, {"enabled": enabled})

    def set_priority(self, rule_id: int, priority: int) -> Dict[str, Any]:
        return self.update(rule_id, {"priority": priority})

    def delete(self, rule_id: int) -> None:
        self.get_by_id(rule_id)
        with db_cursor(commit=True) as cur:
            cur.execute("DELETE FROM rules WHERE id = ?", (rule_id,))

    def list_by_ids(self, rule_ids: List[int]) -> List[Dict[str, Any]]:
        if not rule_ids:
            return []
        placeholders = ",".join("?" for _ in rule_ids)
        with db_cursor() as cur:
            cur.execute(
                f"SELECT * FROM rules WHERE id IN ({placeholders}) ORDER BY priority ASC, id ASC",
                rule_ids,
            )
            rows = cur.fetchall()
        return [self._normalize(row_to_dict(r)) for r in rows]

    def list_enabled_in_group(self, group_id: int) -> List[Dict[str, Any]]:
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT r.* FROM rules r
                INNER JOIN group_members gm ON gm.rule_id = r.id
                WHERE gm.group_id = ? AND r.enabled = 1
                ORDER BY r.priority ASC, r.id ASC
                """,
                (group_id,),
            )
            rows = cur.fetchall()
        return [self._normalize(row_to_dict(r)) for r in rows]

    def count_hits_by_rule(self) -> List[Dict[str, Any]]:
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT r.id AS rule_id, r.rule_name,
                       COALESCE(SUM(h.matched_count), 0) AS hit_count,
                       COUNT(DISTINCT h.run_id) AS run_count
                FROM rules r
                LEFT JOIN hit_details h ON h.rule_id = r.id
                GROUP BY r.id
                ORDER BY hit_count DESC, r.id ASC
                """
            )
            rows = cur.fetchall()
        return rows_to_list(rows)

    @staticmethod
    def _normalize(rule: Dict[str, Any]) -> Dict[str, Any]:
        rule["replace_config"] = parse_json_field(rule.get("replace_config"), {})
        rule["enabled"] = bool(rule.get("enabled"))
        return rule
