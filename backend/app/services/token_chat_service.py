"""Token-authenticated chat — independent of the JWT chat pipeline.

Validates an opaque Chat User access token against `user_token`, then queries
KMRAG with the stored tenant_id + kb_ids, using the caller's session_id as the
KMRAG request_id (conversation/cache key). Does not create ChatSession rows or
touch chat_service.
"""
from __future__ import annotations

import logging

from flask import current_app

from app.constants import TenantStatus
from app.integrations.kmrag_client import KmragQueryRejected, KmragUnavailable
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_token import UserToken
from app.services import document_service, retrieval_service
from app.services.redis_service import check_rate_limit
from app.utils.response_utils import ApiError, unauthorized

logger = logging.getLogger(__name__)

_NO_KB_MESSAGE = (
    "No Knowledge Base is available for this access token yet. "
    "Please contact your Tenant Admin."
)
_KB_NOT_READY_MESSAGE = "Knowledge Base is not ready for chat yet."
_NO_CONTEXT_MESSAGE = "I could not find this information in the assigned Knowledge Base(s)."


def _resolve_token(token: str) -> tuple[UserToken, User, Tenant]:
    """Look up the opaque token and confirm the Chat User + tenant are usable."""
    raw = (token or "").strip()
    if not raw:
        raise unauthorized("A valid access token is required.")

    row = UserToken.query.filter_by(token=raw).first()
    if row is None:
        raise unauthorized("Invalid access token.")

    user = User.query.get(row.user_id)
    if not user or user.deleted_at is not None or not user.is_active:
        raise unauthorized("This access token is no longer valid.")

    tenant = Tenant.query.get(row.tenant_id)
    if (
        not tenant
        or tenant.deleted_at is not None
        or tenant.status != TenantStatus.ACTIVE
    ):
        raise unauthorized("This access token's tenant is not active.")

    # Token row must still match the user binding (guard against stale data).
    if user.tenant_id != row.tenant_id:
        raise unauthorized("Invalid access token.")

    return row, user, tenant


def _apply_rate_limit(tenant_id: str, user_id: str) -> None:
    limit = int(current_app.config.get("RATE_LIMIT_CHAT_PER_MINUTE", 60))
    allowed = check_rate_limit(
        tenant_id=tenant_id,
        user_id=user_id,
        bucket="token_chat",
        limit=limit,
        window=60,
    )
    if not allowed:
        raise ApiError(
            "You are sending requests too quickly. Please slow down and try again.",
            429,
            "rate_limited",
        )


def ask(*, token: str, session_id: str, query: str) -> dict:
    """Authorize via user_token, then run KMRAG chat for the query."""
    row, user, _tenant = _resolve_token(token)
    _apply_rate_limit(row.tenant_id, row.user_id)

    text = (query or "").strip()
    if not text:
        raise ApiError("Query cannot be empty.", 422, "empty_query")

    session_id = (session_id or "").strip()
    if not session_id:
        raise ApiError("session_id is required.", 422, "missing_session_id")

    kb_ids = list(row.kb_ids or [])
    logger.info(
        "TOKEN_CHAT_REQUEST tenant_id=%s user_id=%s session_id=%s kb_ids=%s",
        row.tenant_id, row.user_id, session_id, sorted(kb_ids),
    )

    if not kb_ids:
        return {
            "answer": _NO_KB_MESSAGE,
            "session_id": session_id,
            "context_found": False,
            "user_id": row.user_id,
            "tenant_id": row.tenant_id,
            "kb_ids": [],
        }

    queryable = document_service.queryable_kb_ids(kb_ids)
    if not queryable:
        return {
            "answer": _KB_NOT_READY_MESSAGE,
            "session_id": session_id,
            "context_found": False,
            "user_id": row.user_id,
            "tenant_id": row.tenant_id,
            "kb_ids": kb_ids,
        }

    try:
        retrieval_service.validate_kbs_for_tenant(row.tenant_id, queryable)
        result = retrieval_service.retrieve(
            tenant_id=row.tenant_id,
            kb_ids=queryable,
            query=text,
            request_id=session_id,
            user_id=row.user_id,
        )
    except KmragQueryRejected:
        logger.info("TOKEN_CHAT rejected session_id=%s", session_id)
        return {
            "answer": _KB_NOT_READY_MESSAGE,
            "session_id": session_id,
            "context_found": False,
            "user_id": row.user_id,
            "tenant_id": row.tenant_id,
            "kb_ids": queryable,
        }
    except KmragUnavailable as exc:
        logger.warning("TOKEN_CHAT kmrag unavailable session_id=%s: %s", session_id, exc)
        raise ApiError(
            "The document retrieval service is temporarily unavailable. Please try again.",
            503,
            "service_unavailable",
        ) from exc

    answer = (result.answer or "").strip()
    if not result.context_found or not answer:
        answer = _NO_CONTEXT_MESSAGE

    logger.info(
        "TOKEN_CHAT_RESPONSE session_id=%s context_found=%s",
        session_id, result.context_found,
    )
    return {
        "answer": answer,
        "session_id": session_id,
        "context_found": bool(result.context_found),
        "user_id": row.user_id,
        "tenant_id": row.tenant_id,
        "kb_ids": queryable,
    }
