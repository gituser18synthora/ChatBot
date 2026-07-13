"""Auth helpers + RBAC decorators built on flask-jwt-extended.

`current_user()` loads the authenticated User. `require_roles(...)` gates a
route by role. Tenant scoping is enforced in `tenant_middleware`.
"""
from __future__ import annotations

from functools import wraps

from flask import g
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.constants import Role
from app.models.user import User
from app.utils.response_utils import forbidden, unauthorized


def current_user() -> User:
    """Return the authenticated, active User or raise ApiError."""
    user_id = get_jwt_identity()
    # Cache per request, but only reuse it when it matches the current token's
    # identity. (An outer app context — e.g. in tests — can keep `g` alive across
    # requests, so an unconditional cache would leak one user into another.)
    cached = getattr(g, "_current_user", None)
    if cached is not None and cached.id == user_id:
        return cached
    user = User.query.get(user_id) if user_id else None
    if not user:
        raise unauthorized()
    if not user.is_active:
        raise forbidden("This account has been disabled.")
    g._current_user = user
    return user


def require_roles(*roles: str):
    """Require a valid JWT AND one of the given roles."""
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
    """Require a valid JWT (any role)."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        current_user()
        return fn(*args, **kwargs)

    return wrapper


# Convenience aliases
def super_admin_only(fn):
    return require_roles(Role.SUPER_ADMIN)(fn)


def admin_only(fn):
    return require_roles(Role.SUPER_ADMIN, Role.TENANT_ADMIN)(fn)
