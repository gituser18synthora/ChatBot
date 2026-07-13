"""Consistent JSON envelope + typed API errors.

Every endpoint returns the same shape:

    success: { "success": true,  "data": <payload>, "meta": <optional> }
    error:   { "success": false, "error": { "code": str, "message": str } }
"""
from __future__ import annotations

from typing import Any

from flask import jsonify


def success(data: Any = None, meta: dict | None = None, status: int = 200):
    body: dict[str, Any] = {"success": True, "data": data}
    if meta is not None:
        body["meta"] = meta
    return jsonify(body), status


def paginated(items: list, page: int, per_page: int, total: int, status: int = 200):
    pages = (total + per_page - 1) // per_page if per_page else 0
    return success(
        items,
        meta={"page": page, "per_page": per_page, "total": total, "pages": pages},
        status=status,
    )


class ApiError(Exception):
    """Raised anywhere in a request to return a clean, frontend-safe error.

    `message` is always safe to show a business user. Never put stack traces,
    SQL, KMRAG internals, or credentials here.
    """

    def __init__(self, message: str, status: int = 400, code: str = "bad_request"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code

    def to_response(self):
        return (
            jsonify({"success": False, "error": {"code": self.code, "message": self.message}}),
            self.status,
        )


# ── Convenience constructors for common cases ─────────────────
def unauthorized(message: str = "Your session has expired. Please log in again."):
    return ApiError(message, 401, "unauthorized")


def forbidden(message: str = "You do not have permission to access this resource."):
    return ApiError(message, 403, "forbidden")


def not_found(message: str = "The requested resource was not found."):
    return ApiError(message, 404, "not_found")


def conflict(message: str):
    return ApiError(message, 409, "conflict")


def validation_error(message: str):
    return ApiError(message, 422, "validation_error")


def service_unavailable(message: str = "The service is temporarily unavailable. Please try again."):
    return ApiError(message, 503, "service_unavailable")
