"""Token-authenticated chat endpoint (opaque Chat User access token).

POST /api/v1/token-chat
  Header: X-Access-Token: <opaque token>
  Body:   { session_id, query }

No JWT required — authorization is the opaque token stored in `user_token`.
Independent of /api/v1/chat/*.
"""
from __future__ import annotations

from flask import Blueprint, request

from app.schemas import load_body
from app.schemas.token_chat_schema import TokenChatSchema
from app.services import token_chat_service
from app.utils.response_utils import success, unauthorized

bp = Blueprint("token_chat", __name__, url_prefix="/api/v1")

_HEADER = "X-Access-Token"


def _token_from_headers() -> str:
    """Read the opaque access token from headers only (never from the body)."""
    raw = (request.headers.get(_HEADER) or "").strip()
    if raw:
        return raw
    # Also accept standard Bearer form for API clients that prefer Authorization.
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    raise unauthorized("A valid access token is required in the X-Access-Token header.")


@bp.post("/token-chat")
def token_chat():
    data = load_body(TokenChatSchema())
    return success(
        token_chat_service.ask(
            token=_token_from_headers(),
            session_id=data["session_id"],
            query=data["query"],
        )
    )
