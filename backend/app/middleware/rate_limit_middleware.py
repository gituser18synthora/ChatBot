"""Per-user, tenant-scoped rate limiting decorator."""
from __future__ import annotations

from functools import wraps

from flask import current_app

from app.middleware.auth_middleware import current_user
from app.services.redis_service import check_rate_limit
from app.utils.response_utils import ApiError


def rate_limit(bucket: str, config_key: str):
    """Limit calls per authenticated user using the configured per-minute cap."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            limit = int(current_app.config.get(config_key, 60))
            allowed = check_rate_limit(
                tenant_id=user.tenant_id or "none",
                user_id=user.id,
                bucket=bucket,
                limit=limit,
                window=60,
            )
            if not allowed:
                raise ApiError(
                    "You are sending requests too quickly. Please slow down and try again.",
                    429,
                    "rate_limited",
                )
            return fn(*args, **kwargs)

        return wrapper

    return decorator
