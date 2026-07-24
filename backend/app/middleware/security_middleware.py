"""Default-deny auth, CSRF, and security headers."""
from __future__ import annotations

import hmac

from flask import current_app, request
from flask_jwt_extended import get_jwt, verify_jwt_in_request

from app.middleware.auth_middleware import current_user
from app.utils.response_utils import ApiError, unauthorized

_PUBLIC_ENDPOINTS = {
    "auth.login",
    "auth.refresh",
    "token_chat.token_chat",
    "health",
}
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def register_security_middleware(app):
    @app.before_request
    def _default_deny_and_csrf():
        if request.method == "OPTIONS":
            return None
        if not request.path.startswith("/api/"):
            return None
        if request.endpoint in _PUBLIC_ENDPOINTS:
            if request.endpoint == "auth.refresh":
                _validate_csrf()
            return None
        verify_jwt_in_request()
        current_user()
        if request.method in _UNSAFE_METHODS:
            _validate_csrf()
        return None

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response


def _validate_csrf() -> None:
    cookie_name = current_app.config["AUTH_CSRF_COOKIE_NAME"]
    header_name = current_app.config["AUTH_CSRF_HEADER_NAME"]
    cookie_value = request.cookies.get(cookie_name, "")
    header_value = request.headers.get(header_name, "")
    token_value = ""
    try:
        token_value = get_jwt().get("csrf", "")
    except RuntimeError:
        pass
    expected = token_value if request.headers.get("Authorization", "").startswith("Bearer ") else cookie_value
    if not expected or not header_value or not hmac.compare_digest(expected, header_value):
        raise ApiError("CSRF validation failed.", 403, "csrf_failed")


def set_csrf_cookie(response, csrf_token: str) -> None:
    response.set_cookie(
        current_app.config["AUTH_CSRF_COOKIE_NAME"],
        csrf_token,
        httponly=False,
        secure=current_app.config["AUTH_COOKIE_SECURE"],
        samesite=current_app.config["AUTH_COOKIE_SAMESITE"],
        domain=current_app.config["AUTH_COOKIE_DOMAIN"],
        path="/",
    )


def clear_csrf_cookie(response) -> None:
    response.delete_cookie(
        current_app.config["AUTH_CSRF_COOKIE_NAME"],
        domain=current_app.config["AUTH_COOKIE_DOMAIN"],
        path="/",
    )
