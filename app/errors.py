"""统一错误处理。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from flask import Flask, jsonify


class APIError(Exception):
    """业务异常基类。"""

    status_code: int = 400
    error_code: str = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        error_code: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        if error_code:
            self.error_code = error_code
        if status_code:
            self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


class ValidationError(APIError):
    status_code = 400
    error_code = "validation_error"


class NotFoundError(APIError):
    status_code = 404
    error_code = "not_found"


class ConflictError(APIError):
    status_code = 409
    error_code = "conflict"


class RuleDisabledError(APIError):
    status_code = 400
    error_code = "rule_disabled"


class RegexCompileError(APIError):
    status_code = 400
    error_code = "regex_invalid"


def _json_error_response(error: APIError):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def _handle_api_error(error: APIError):
        return _json_error_response(error)

    @app.errorhandler(404)
    def _handle_404(_error):
        return _json_error_response(
            APIError("资源不存在", error_code="not_found", status_code=404)
        )

    @app.errorhandler(405)
    def _handle_405(_error):
        return _json_error_response(
            APIError("方法不允许", error_code="method_not_allowed", status_code=405)
        )

    @app.errorhandler(500)
    def _handle_500(error):
        return _json_error_response(
            APIError(
                "服务器内部错误",
                error_code="internal_error",
                status_code=500,
                details={"info": str(error)},
            )
        )
