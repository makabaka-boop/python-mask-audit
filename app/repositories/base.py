"""仓储辅助函数。"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, Optional

from ..database import db_cursor


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def rows_to_list(rows) -> list:
    return [row_to_dict(r) for r in rows]


def parse_json_field(value: Any, default=None):
    if default is None:
        default = {}
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
