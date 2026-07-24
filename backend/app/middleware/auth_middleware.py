"""Auth helpers and role decorators built on server-side sessions."""
from __future__ import annotations

from functools import wraps

from flask import g
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

from app.constants import Role
from app.extensions import db
from app.models.user import User
from app.services import auth_service
from app.utils.response_utils import forbidden, unauthorized


def current_user() -> User:
    user_id = get_jwt_identity()
    claims = get_jwt()
    cached = getattr(g, "_current_user", None)
    if cached is not None and cached.id == user_id:
        return cached
    auth_service.get_active_session(claims.get("sid"), user_id)
    user = User.query.get(user_id) if user_id else None
    if not user or user.deleted_at is not None:
        raise unauthorized()
    if not user.is_active:
        raise forbidden("This account has been disabled.")
    g._current_user = user
    db.session.commit()
    return user


def require_roles(*roles: str):
    allowed = set(roles) or set(Role.ALL)

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = current_user()
            if user.role not in allowed:
                raise forbidden()
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        current_user()
        return fn(*args, **kwargs)

    return wrapper


def super_admin_only(fn):
    return require_roles(Role.SUPER_ADMIN)(fn)


def admin_only(fn):
    return require_roles(Role.SUPER_ADMIN, Role.TENANT_ADMIN)(fn)
