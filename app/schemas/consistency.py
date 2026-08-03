"""一致性自检相关 Schema。"""
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class CheckItem(BaseModel):
    """单项检查结果。"""

    model_config = ConfigDict(from_attributes=True)

    check_name: str
    passed: bool
    issue_count: int = 0
    details: List[Dict[str, Any]] = Field(default_factory=list)


class ConsistencyReport(BaseModel):
    """自检报告。"""

    model_config = ConfigDict(from_attributes=True)

    all_passed: bool
    total_issues: int = 0
    checks: List[CheckItem] = Field(default_factory=list)
