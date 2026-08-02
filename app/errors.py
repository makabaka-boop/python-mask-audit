"""统一错误响应：{"error_code": "...", "message": "...", "details": {...}}"""

from flask import jsonify
from werkzeug.exceptions import HTTPException


class ApiError(Exception):
    def __init__(self, error_code: str, message: str, status: int = 400, details: dict = None):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status = status
        self.details = details or {}


def not_found(message: str, details: dict = None) -> ApiError:
    return ApiError("NOT_FOUND", message, 404, details)


def validation_error(message: str, details: dict = None) -> ApiError:
    return ApiError("VALIDATION_ERROR", message, 400, details)


def conflict_error(message: str, details: dict = None) -> ApiError:
    return ApiError("CONFLICT", message, 409, details)


def register_error_handlers(app) -> None:
    @app.errorhandler(ApiError)
    def handle_api_error(err: ApiError):
        return jsonify({
            "error_code": err.error_code,
            "message": err.message,
            "details": err.details,
        }), err.status

    @app.errorhandler(HTTPException)
    def handle_http_error(err: HTTPException):
        return jsonify({
            "error_code": "HTTP_ERROR",
            "message": err.description or err.name,
            "details": {"status": err.code},
        }), err.code

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception):
        return jsonify({
            "error_code": "INTERNAL_ERROR",
            "message": "服务内部错误",
            "details": {"error": str(err)},
        }), 500
