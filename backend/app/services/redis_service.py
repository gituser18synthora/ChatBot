"""Redis helpers: tenant-scoped cache keys, JWT revocation, rate limiting.

Every key includes tenant context so one tenant's cache can never collide with
another's. Redis is never the source of truth — only a cache / ephemeral store.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from flask import current_app

from app.extensions import redis_client

logger = logging.getLogger(__name__)


# ── Key builders (always tenant-scoped where a tenant exists) ──
def kb_key(tenant_id: str, kb_id: str) -> str:
    return f"tenant:{tenant_id}:kb:{kb_id}"


def tenant_key(tenant_id: str) -> str:
    return f"tenant:{tenant_id}:meta"


def rate_limit_key(tenant_id: str, user_id: str, bucket: str) -> str:
    return f"tenant:{tenant_id}:rate_limit:{bucket}:{user_id}"


def revoked_token_key(jti: str) -> str:
    return f"jwt:revoked:{jti}"


# ── Generic cache with graceful degradation ───────────────────
def cache_get_json(key: str) -> Any | None:
    try:
        raw = redis_client.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:  # cache must never break a request
        logger.warning("redis get failed key=%s: %s", key, exc)
        return None


def cache_set_json(key: str, value: Any, ttl: int) -> None:
    try:
        redis_client.setex(key, ttl, json.dumps(value))
    except Exception as exc:
        logger.warning("redis set failed key=%s: %s", key, exc)


def cache_delete(*keys: str) -> None:
    try:
        if keys:
            redis_client.delete(*keys)
    except Exception as exc:
        logger.warning("redis delete failed: %s", exc)


# ── JWT revocation (logout / token blocklist) ─────────────────
def revoke_token(jti: str, ttl_seconds: int) -> None:
    try:
        redis_client.setex(revoked_token_key(jti), ttl_seconds, "1")
    except Exception as exc:
        logger.warning("token revoke failed jti=%s: %s", jti, exc)


def is_token_revoked(jti: str) -> bool:
    try:
        return redis_client.exists(revoked_token_key(jti)) == 1
    except Exception as exc:
        # Fail safe: if we can't check, do not lock everyone out.
        logger.warning("token revoke check failed jti=%s: %s", jti, exc)
        return False


# ── Sliding-window rate limiting ──────────────────────────────
def check_rate_limit(tenant_id: str, user_id: str, bucket: str, limit: int, window: int = 60) -> bool:
    """Return True if the call is allowed, False if the limit is exceeded.

    Fails open (allows) if Redis is unavailable so an outage doesn't block users.
    """
    key = rate_limit_key(tenant_id or "none", user_id, bucket)
    try:
        now = int(time.time())
        window_start = now - window
        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {f"{now}:{time.time_ns()}": now})
        pipe.zcard(key)
        pipe.expire(key, window)
        _, _, count, _ = pipe.execute()
        return int(count) <= limit
    except Exception as exc:
        logger.warning("rate limit check failed key=%s: %s", key, exc)
        return True
