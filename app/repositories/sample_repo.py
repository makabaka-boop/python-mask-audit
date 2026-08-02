"""样例文本仓储。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..database import db_cursor
from ..errors import NotFoundError
from .base import row_to_dict, rows_to_list


class SampleRepository:
    def create(
        self,
        sample_name: str,
        raw_text: str,
        sample_category: Optional[str] = None,
        expected_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO samples (sample_name, sample_category, raw_text, expected_note)
                VALUES (?, ?, ?, ?)
                """,
                (sample_name, sample_category, raw_text, expected_note),
            )
            sample_id = cur.lastrowid
        return self.get_by_id(sample_id)

    def get_by_id(self, sample_id: int) -> Dict[str, Any]:
        with db_cursor() as cur:
            cur.execute("SELECT * FROM samples WHERE id = ?", (sample_id,))
            row = cur.fetchone()
        if row is None:
            raise NotFoundError(
                f"样例 {sample_id} 不存在", details={"sample_id": sample_id}
            )
        return row_to_dict(row)

    def list(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM samples"
        params: list = []
        if category:
            sql += " WHERE sample_category = ?"
            params.append(category)
        sql += " ORDER BY id DESC"
        with db_cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return rows_to_list(rows)

    def delete(self, sample_id: int) -> None:
        self.get_by_id(sample_id)
        with db_cursor(commit=True) as cur:
            cur.execute("DELETE FROM samples WHERE id = ?", (sample_id,))
