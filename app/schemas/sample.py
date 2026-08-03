"""样例文本相关 Schema。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SampleCreate(BaseModel):
    """创建样例文本请求。"""

    model_config = ConfigDict(from_attributes=True)

    sample_name: str = Field(min_length=1)
    sample_category: str = "general"
    raw_text: str = Field(min_length=1)
    expected_note: str = ""


class SampleUpdate(BaseModel):
    """更新样例文本请求，所有字段可选。"""

    model_config = ConfigDict(from_attributes=True)

    sample_name: Optional[str] = Field(default=None, min_length=1)
    sample_category: Optional[str] = None
    raw_text: Optional[str] = Field(default=None, min_length=1)
    expected_note: Optional[str] = None


class SampleResponse(BaseModel):
    """样例文本响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sample_name: str
    sample_category: str
    raw_text: str
    expected_note: str
    created_at: Optional[datetime] = None
