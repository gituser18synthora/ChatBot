from __future__ import annotations

from flask import Blueprint, request

from app.middleware.auth_middleware import admin_only, current_user
from app.middleware.tenant_middleware import resolve_tenant_scope
from app.models.audit_log import AuditLog
from app.utils.response_utils import paginated

bp = Blueprint("audit_logs", __name__, url_prefix="/api/v1/audit-logs")


@bp.get("")
@admin_only
def list_audit_logs():
    user = current_user()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    scope = resolve_tenant_scope(user, request.args.get("tenant_id"))

    q = AuditLog.query
    # Tenant admins only ever see their own tenant's audit trail.
    if scope is not None:
        q = q.filter(AuditLog.tenant_id == scope)
    if request.args.get("action"):
        q = q.filter(AuditLog.action == request.args.get("action"))
    if request.args.get("entity_type"):
        q = q.filter(AuditLog.entity_type == request.args.get("entity_type"))
    q = q.order_by(AuditLog.created_at.desc())

    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return paginated([a.to_dict() for a in items], page, per_page, total)
