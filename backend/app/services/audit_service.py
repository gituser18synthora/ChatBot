"""Audit logging. Records who did what, with safe before/after snapshots.

Never records passwords, tokens, secrets, or full document content.
"""
from __future__ import annotations

import logging

from flask import request

from app.extensions import db
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

_SENSITIVE = {"password", "password_hash", "token", "access_token", "refresh_token", "secret"}


def _scrub(data: dict | None) -> dict | None:
    if not data:
        return data
    return {k: ("***" if k.lower() in _SENSITIVE else v) for k, v in data.items()}


def log_action(
    *,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
    old_data: dict | None = None,
    new_data: dict | None = None,
    commit: bool = True,
) -> AuditLog:
    ip = None
    ua = None
    try:
        if request:
            ip = request.headers.get("X-Forwarded-For", request.remote_addr)
            ua = (request.headers.get("User-Agent") or "")[:400]
    except RuntimeError:
        pass  # outside request context (e.g. seed scripts)

    entry = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        tenant_id=tenant_id,
        user_id=user_id,
        old_data=_scrub(old_data),
        new_data=_scrub(new_data),
        ip_address=ip,
        user_agent=ua,
    )
    db.session.add(entry)
    if commit:
        db.session.commit()
    return entry
