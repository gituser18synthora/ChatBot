"""Token-authenticated chat endpoint (opaque Chat User access token).

POST /api/v1/token-chat
  Body: { token, session_id, query }

No JWT required — authorization is the opaque token stored in `user_token`.
Independent of /api/v1/chat/*.
"""
from __future__ import annotations

from flask import Blueprint

from app.schemas import load_body
from app.schemas.token_chat_schema import TokenChatSchema
from app.services import token_chat_service
from app.utils.response_utils import success

bp = Blueprint("token_chat", __name__, url_prefix="/api/v1")


@bp.post("/token-chat")
def token_chat():
    data = load_body(TokenChatSchema())
    return success(
        token_chat_service.ask(
            token=data["token"],
            session_id=data["session_id"],
            query=data["query"],
        )
    )
