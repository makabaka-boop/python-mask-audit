"""规则冲突相关 Schema。"""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ConflictItem(BaseModel):
    """单条冲突信息。"""

    model_config = ConfigDict(from_attributes=True)

    rule_ids: List[int] = Field(default_factory=list)
    conflict_type: str
    message: str
    severity: str


class ConflictResponse(BaseModel):
    """冲突检测响应。"""

    model_config = ConfigDict(from_attributes=True)

    group_id: int
    total: int
    conflicts: List[ConflictItem] = Field(default_factory=list)


class ReplayRegressionRequest(BaseModel):
    """回放回归请求。"""

    model_config = ConfigDict(from_attributes=True)

    sample_id: int
    group_id: int


class DiffDetail(BaseModel):
    """单条规则的差异详情。"""

    model_config = ConfigDict(from_attributes=True)

    rule_id: int
    rule_name: str = ""
    diff_fields: List[str] = Field(default_factory=list)


class ReplayRegressionResponse(BaseModel):
    """回放回归响应。"""

    model_config = ConfigDict(from_attributes=True)

    sample_id: int
    group_id: int
    snapshot_id: int
    run_id: int
    historical_output: str
    current_output: str
    is_consistent: bool
    diff_reasons: List[str] = Field(default_factory=list)
    rules_added: List[int] = Field(default_factory=list)
    rules_removed: List[int] = Field(default_factory=list)
    rules_changed: List[DiffDetail] = Field(default_factory=list)
    rules_unchanged: List[int] = Field(default_factory=list)
