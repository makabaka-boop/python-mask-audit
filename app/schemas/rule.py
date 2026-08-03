"""规则相关 Schema。"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

MatchType = Literal["exact", "contains", "regex"]
ReplaceStrategy = Literal["fixed", "keep_edges", "middle_mask"]


class KeepEdgesConfig(BaseModel):
    """keep_edges 替换策略配置。"""

    model_config = ConfigDict(from_attributes=True)

    left: int = Field(default=1, ge=0)
    right: int = Field(default=1, ge=0)
    mask_char: str = Field(default="*", max_length=1)


class FixedConfig(BaseModel):
    """fixed 替换策略配置。"""

    model_config = ConfigDict(from_attributes=True)

    replacement: str = Field(default="***")


class MiddleMaskConfig(BaseModel):
    """middle_mask 替换策略配置。"""

    model_config = ConfigDict(from_attributes=True)

    mask_char: str = Field(default="*", max_length=1)


class RuleCreate(BaseModel):
    """创建规则请求。"""

    model_config = ConfigDict(from_attributes=True)

    rule_name: str
    field_type: str = "text"
    match_type: MatchType
    match_value: str = Field(min_length=1)
    replace_strategy: ReplaceStrategy
    replace_config: dict = Field(default_factory=dict)
    priority: int = Field(default=100, ge=0)
    enabled: bool = True


class RuleUpdate(BaseModel):
    """更新规则请求，所有字段可选。"""

    model_config = ConfigDict(from_attributes=True)

    rule_name: Optional[str] = None
    field_type: Optional[str] = None
    match_type: Optional[MatchType] = None
    match_value: Optional[str] = Field(default=None, min_length=1)
    replace_strategy: Optional[ReplaceStrategy] = None
    replace_config: Optional[dict] = None
    priority: Optional[int] = Field(default=None, ge=0)
    enabled: Optional[bool] = None


class RuleResponse(BaseModel):
    """规则响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_name: str
    field_type: str
    match_type: MatchType
    match_value: str
    replace_strategy: ReplaceStrategy
    replace_config: dict
    priority: int
    enabled: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RuleToggle(BaseModel):
    """启用/禁用规则请求。"""

    model_config = ConfigDict(from_attributes=True)

    enabled: bool


class RulePriorityUpdate(BaseModel):
    """更新规则优先级请求。"""

    model_config = ConfigDict(from_attributes=True)

    priority: int = Field(ge=0)


class RulePreviewRequest(BaseModel):
    """规则预览请求，仅用于预览，不产生演练记录。"""

    model_config = ConfigDict(from_attributes=True)

    sample_id: Optional[int] = None
    rule_id: int
    input_text: Optional[str] = None

    @model_validator(mode="after")
    def _check_source(self) -> "RulePreviewRequest":
        if self.sample_id is None and not self.input_text:
            raise ValueError("sample_id 与 input_text 必须提供其中之一")
        return self
