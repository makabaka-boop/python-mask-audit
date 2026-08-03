"""演练记录与命中明细仓储。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..database import db_cursor
from ..errors import NotFoundError
from .base import row_to_dict, rows_to_list


class RunRepository:
    def create(
        self,
        *,
        input_text: str,
        output_text: str,
        hit_count: int,
        sample_id: Optional[int] = None,
        rule_id: Optional[int] = None,
        group_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO runs (sample_id, rule_id, group_id, input_text, output_text, hit_count)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (sample_id, rule_id, group_id, input_text, output_text, hit_count),
            )
            run_id = cur.lastrowid
        return self.get_by_id(run_id)

    def get_by_id(self, run_id: int) -> Dict[str, Any]:
        with db_cursor() as cur:
            cur.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
            row = cur.fetchone()
        if row is None:
            raise NotFoundError(f"演练记录 {run_id} 不存在", details={"run_id": run_id})
        return row_to_dict(row)

    def list(
        self,
        sample_id: Optional[int] = None,
        rule_id: Optional[int] = None,
        group_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM runs WHERE 1=1"
        params: list = []
        if sample_id is not None:
            sql += " AND sample_id = ?"
            params.append(sample_id)
        if rule_id is not None:
            sql += " AND rule_id = ?"
            params.append(rule_id)
        if group_id is not None:
            sql += " AND group_id = ?"
            params.append(group_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with db_cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return rows_to_list(rows)

    def add_hit_detail(
        self,
        run_id: int,
        rule_id: Optional[int],
        matched_count: int,
        before_fragment: str,
        after_fragment: str,
    ) -> int:
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO hit_details (run_id, rule_id, matched_count, before_fragment, after_fragment)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, rule_id, matched_count, before_fragment, after_fragment),
            )
            return cur.lastrowid

    def list_hit_details(self, run_id: int) -> List[Dict[str, Any]]:
        with db_cursor() as cur:
            cur.execute(
                "SELECT * FROM hit_details WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            )
            rows = cur.fetchall()
        return rows_to_list(rows)

    def latest_by_sample(self, sample_id: int) -> Optional[Dict[str, Any]]:
        with db_cursor() as cur:
            cur.execute(
                "SELECT * FROM runs WHERE sample_id = ? ORDER BY id DESC LIMIT 1",
                (sample_id,),
            )
            row = cur.fetchone()
        return row_to_dict(row)

    def latest_by_group(self, group_id: int) -> Optional[Dict[str, Any]]:
        with db_cursor() as cur:
            cur.execute(
                "SELECT * FROM runs WHERE group_id = ? ORDER BY id DESC LIMIT 1",
                (group_id,),
            )
            row = cur.fetchone()
        return row_to_dict(row)
