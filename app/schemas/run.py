"""演练执行与回归相关 Schema。"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GroupRunRequest(BaseModel):
    """按分组执行演练请求。"""

    model_config = ConfigDict(from_attributes=True)

    sample_id: int
    group_id: int


class SingleRuleRunRequest(BaseModel):
    """单条规则演练请求。"""

    model_config = ConfigDict(from_attributes=True)

    sample_id: Optional[int] = None
    rule_id: int
    input_text: Optional[str] = None

    @model_validator(mode="after")
    def _check_source(self) -> "SingleRuleRunRequest":
        if self.sample_id is None and not self.input_text:
            raise ValueError("sample_id 与 input_text 必须提供其中之一")
        return self


class HitDetailResponse(BaseModel):
    """命中明细响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    rule_id: Optional[int] = None
    matched_count: int
    before_fragment: str
    after_fragment: str


class RunResponse(BaseModel):
    """演练记录响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sample_id: Optional[int] = None
    rule_id: Optional[int] = None
    group_id: Optional[int] = None
    input_text: str
    output_text: str
    hit_count: int
    snapshot_id: Optional[int] = None
    executed_at: Optional[datetime] = None


class RunDetailResponse(RunResponse):
    """演练详情，包含命中明细列表。"""

    hit_details: List[HitDetailResponse] = Field(default_factory=list)


class RuleStats(BaseModel):
    """规则统计信息。"""

    model_config = ConfigDict(from_attributes=True)

    rule_id: int
    rule_name: str
    total_runs: int = 0
    total_hits: int = 0
    last_run_at: Optional[datetime] = None


class RegressionResult(BaseModel):
    """回归对比结果。"""

    model_config = ConfigDict(from_attributes=True)

    snapshot_id: int
    group_id: Optional[int] = None
    rules_changed: List[int] = Field(default_factory=list)
    rules_added: List[int] = Field(default_factory=list)
    rules_removed: List[int] = Field(default_factory=list)
    rules_unchanged: List[int] = Field(default_factory=list)
    is_passed: bool
