from __future__ import annotations
"""统一错误处理。"""
from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """业务错误基类。"""

    def __init__(self, error_code: str, message: str, details: dict | None = None,
                 status_code: int = 400):
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        self.status_code = status_code
        super().__init__(message)


class ValidationError(AppError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__("VALIDATION_ERROR", message, details, 422)


class NotFoundError(AppError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__("NOT_FOUND", message, details, 404)


class ConflictError(AppError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__("CONFLICT", message, details, 409)


class RuleDisabledError(AppError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__("RULE_DISABLED", message, details, 400)


class RegexCompileError(AppError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__("REGEX_COMPILE_ERROR", message, details, 422)


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
        },
    )


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_ERROR",
            "message": "服务器内部错误",
            "details": {"error": str(exc)},
        },
    )
