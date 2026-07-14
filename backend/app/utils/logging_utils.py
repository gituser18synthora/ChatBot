"""Structured logging + per-request correlation IDs.

A `request_id` is attached to every request (from the inbound
`X-Request-ID` header or freshly generated) and injected into every log record
so operations can be traced end-to-end. Secrets are never logged.
"""
from __future__ import annotations

import logging
from contextvars import ContextVar

from pythonjsonlogger import jsonlogger

from app.utils.uuid_utils import new_uuid

_request_id: ContextVar[str] = ContextVar("request_id", default="-")

# Keys we must never let through into logs even if a caller passes them.
_REDACTED_KEYS = {
    "password", "password_hash", "authorization", "access_token", "refresh_token",
    "token", "openai_api_key", "api_key", "secret", "jwt", "postgres_password",
}


def set_request_id(value: str | None) -> str:
    # Always a valid UUID: an inbound X-Request-ID from a proxy/client may be a
    # non-UUID or longer than 36 chars, and this id is persisted in CHAR(36)
    # columns (e.g. documents.kmrag_request_id). Accept the header only when it
    # is a valid UUID; otherwise mint a fresh one.
    from app.utils.uuid_utils import is_valid_uuid, new_uuid

    rid = value if is_valid_uuid(value) else new_uuid()
    _request_id.set(rid)
    return rid


def get_request_id() -> str:
    return _request_id.get()


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def configure_logging(level: str = "INFO", as_json: bool = True) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(_RequestIdFilter())
    if as_json:
        fmt = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s"
        )
    else:
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s [%(request_id)s] %(message)s"
        )
    handler.setFormatter(fmt)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def redact(data: dict) -> dict:
    """Return a shallow copy with sensitive values masked, for safe logging."""
    out = {}
    for k, v in (data or {}).items():
        out[k] = "***" if k.lower() in _REDACTED_KEYS else v
    return out
