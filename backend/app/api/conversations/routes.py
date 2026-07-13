from __future__ import annotations

from flask import Blueprint, request

from app.middleware.auth_middleware import admin_only, current_user
from app.middleware.tenant_middleware import resolve_tenant_scope
from app.services import chat_service
from app.utils.response_utils import paginated, success

bp = Blueprint("conversations", __name__, url_prefix="/api/v1/admin/conversations")


@bp.get("")
@admin_only
def list_conversations():
    user = current_user()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    scope = resolve_tenant_scope(user, request.args.get("tenant_id"))
    items, total = chat_service.list_tenant_sessions(scope, page, per_page, request.args.get("search"))
    return paginated(items, page, per_page, total)


@bp.get("/<session_id>")
@admin_only
def get_conversation(session_id):
    # get_session_with_messages already allows admins to view within their tenant.
    return success(chat_service.get_session_with_messages(current_user(), session_id))
