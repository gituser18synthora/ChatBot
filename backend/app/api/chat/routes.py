from __future__ import annotations

from flask import Blueprint, request

from app.middleware.auth_middleware import current_user, require_auth
from app.middleware.rate_limit_middleware import rate_limit
from app.schemas import load_body
from app.schemas.chat_schema import MessageCreateSchema, SessionCreateSchema, SessionUpdateSchema
from app.services import chat_service, kb_service, user_kb_service
from app.utils.response_utils import paginated, success

bp = Blueprint("chat", __name__, url_prefix="/api/v1/chat")


@bp.get("/availability")
@require_auth
def chat_availability():
    """Whether the signed-in user's tenant has any Knowledge Base. Chat requires
    at least one; the UI uses this to gate the 'Open Chat' / 'New Chat' actions."""
    return success({"has_knowledge_base": kb_service.tenant_has_kb(current_user().tenant_id)})


@bp.get("/knowledge-bases")
@require_auth
def selectable_knowledge_bases():
    """The KBs the signed-in user may ground a chat in. Chat Users get only
    admin-assigned KBs; Tenant Admins may see all tenant KBs when unscoped."""
    return success(user_kb_service.selectable_kbs_for_user(current_user()))


@bp.post("/sessions")
@require_auth
def create_session():
    data = load_body(SessionCreateSchema())
    session = chat_service.create_session(current_user(), data.get("title"), data.get("kb_ids", []))
    return success(session.to_dict(kb_ids=data.get("kb_ids", [])), status=201)


@bp.get("/sessions")
@require_auth
def list_sessions():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    items, total = chat_service.list_sessions(current_user(), page, per_page, request.args.get("search"))
    return paginated([s.to_dict() for s in items], page, per_page, total)


@bp.get("/sessions/<session_id>")
@require_auth
def get_session(session_id):
    return success(chat_service.get_session_with_messages(current_user(), session_id))


@bp.put("/sessions/<session_id>")
@require_auth
def rename_session(session_id):
    data = load_body(SessionUpdateSchema())
    return success(chat_service.rename_session(current_user(), session_id, data["title"]).to_dict())


@bp.delete("/sessions/<session_id>")
@require_auth
def delete_session(session_id):
    chat_service.delete_session(current_user(), session_id)
    return success({"message": "Conversation deleted."})


@bp.post("/sessions/<session_id>/messages")
@require_auth
@rate_limit("chat", "RATE_LIMIT_CHAT_PER_MINUTE")
def post_message(session_id):
    data = load_body(MessageCreateSchema())
    # Returns {assistant_message, session_id, session_title} — the title may have
    # just been auto-generated from the first user message.
    return success(chat_service.post_message(current_user(), session_id, data["message"]))
