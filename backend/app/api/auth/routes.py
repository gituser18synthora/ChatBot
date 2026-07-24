from __future__ import annotations

from flask import Blueprint, current_app, request
from flask_jwt_extended import get_jwt, set_access_cookies, set_refresh_cookies, unset_jwt_cookies

from app.middleware.auth_middleware import current_user, require_auth
from app.middleware.security_middleware import clear_csrf_cookie, set_csrf_cookie
from app.schemas import load_body
from app.schemas.auth_schema import LoginSchema
from app.services import auth_service
from app.utils.response_utils import success

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


def _cookie_response(payload: dict, message: str = "OK"):
    access = payload.pop("access_token")
    refresh = payload.pop("refresh_token")
    csrf = payload.pop("csrf_token")
    response, status = success({"message": message, "user": payload["user"], "session_id": payload["session_id"]})
    set_access_cookies(response, access)
    set_refresh_cookies(response, refresh)
    set_csrf_cookie(response, csrf)
    return response, status


@bp.post("/login")
def login():
    data = load_body(LoginSchema())
    return _cookie_response(auth_service.authenticate(data["email"], data["password"]), "Logged in.")


@bp.post("/logout")
@require_auth
def logout():
    user = current_user()
    auth_service.logout_current(user, get_jwt())
    response, status = success({"message": "Logged out."})
    unset_jwt_cookies(response)
    clear_csrf_cookie(response)
    return response, status


@bp.post("/logout-all")
@require_auth
def logout_all():
    user = current_user()
    auth_service.logout_all(user)
    response, status = success({"message": "Logged out on all devices."})
    unset_jwt_cookies(response)
    clear_csrf_cookie(response)
    return response, status


@bp.get("/me")
@require_auth
def me():
    return success({"user": current_user().to_dict()})


@bp.post("/refresh")
def refresh():
    token = request.cookies.get(current_app.config["JWT_REFRESH_COOKIE_NAME"])
    return _cookie_response(auth_service.rotate_refresh_token(token), "Session refreshed.")
