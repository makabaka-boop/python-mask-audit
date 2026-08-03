"""审计查询相关 Schema。"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ConfigVersion(BaseModel):
    """规则在某快照中的配置版本。"""

    model_config = ConfigDict(from_attributes=True)

    snapshot_id: int
    rule_id: int
    rule_name: str
    match_type: str
    match_value: str
    replace_strategy: str
    replace_config: Dict[str, Any] = Field(default_factory=dict)
    priority: int
    enabled: bool
    recorded_at: Optional[str] = None


class RuleAuditView(BaseModel):
    """规则维度审计视图。"""

    model_config = ConfigDict(from_attributes=True)

    rule_id: int
    current_config: Dict[str, Any] = Field(default_factory=dict)
    config_versions: List[ConfigVersion] = Field(default_factory=list)
    total_hits: int = 0
    last_hit_at: Optional[datetime] = None


class RuleHitDistribution(BaseModel):
    """样例维度下各规则命中分布。"""

    model_config = ConfigDict(from_attributes=True)

    rule_id: int
    rule_name: str = ""
    total_hits: int = 0
    hit_count: int = 0
    last_hit_at: Optional[datetime] = None


class SampleAuditView(BaseModel):
    """样例维度审计视图。"""

    model_config = ConfigDict(from_attributes=True)

    sample_id: int
    sample_name: str = ""
    latest_run: Optional[Dict[str, Any]] = None
    latest_regression: Optional[Dict[str, Any]] = None
    rule_hit_distribution: List[RuleHitDistribution] = Field(default_factory=list)


class SnapshotMemberSummary(BaseModel):
    """快照成员摘要。"""

    model_config = ConfigDict(from_attributes=True)

    snapshot_id: int
    created_at: Optional[str] = None
    rule_ids: List[int] = Field(default_factory=list)
    label: str = ""


class MemberChangeDiff(BaseModel):
    """成员变化差异摘要。"""

    model_config = ConfigDict(from_attributes=True)

    added: List[int] = Field(default_factory=list)
    removed: List[int] = Field(default_factory=list)
    latest_snapshot_id: Optional[int] = None
    execution_diff_summary: str = ""


class GroupAuditView(BaseModel):
    """分组维度审计视图。"""

    model_config = ConfigDict(from_attributes=True)

    group_id: int
    group_name: str = ""
    current_members: List[int] = Field(default_factory=list)
    historical_snapshots: List[SnapshotMemberSummary] = Field(default_factory=list)
    member_change_diff: Optional[MemberChangeDiff] = None
