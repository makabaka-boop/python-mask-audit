"""通用响应 Schema。"""
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应包装。"""

    model_config = ConfigDict(from_attributes=True)

    success: bool = True
    code: int = 0
    message: str = "ok"
    data: Optional[T] = None


class ErrorResponse(BaseModel):
    """错误响应。"""

    model_config = ConfigDict(from_attributes=True)

    success: bool = False
    error_code: str
    message: str
    details: dict[str, Any] = {}
