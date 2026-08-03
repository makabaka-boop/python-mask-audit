"""规则分组相关 Schema。"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.rule import RuleResponse


class GroupCreate(BaseModel):
    """创建分组请求。"""

    model_config = ConfigDict(from_attributes=True)

    group_name: str = Field(min_length=1)
    description: str = ""


class GroupUpdate(BaseModel):
    """更新分组请求，所有字段可选。"""

    model_config = ConfigDict(from_attributes=True)

    group_name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None


class GroupResponse(BaseModel):
    """分组响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    group_name: str
    description: str
    created_at: Optional[datetime] = None


class GroupMemberRequest(BaseModel):
    """添加/移除分组成员请求。"""

    model_config = ConfigDict(from_attributes=True)

    group_id: int
    rule_id: int


class GroupMemberResponse(BaseModel):
    """分组成员响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    rule_id: int
    created_at: Optional[datetime] = None


class GroupWithRules(GroupResponse):
    """分组及其包含的规则列表。"""

    rules: List[RuleResponse] = Field(default_factory=list)
