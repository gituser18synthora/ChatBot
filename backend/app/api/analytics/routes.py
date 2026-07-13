from __future__ import annotations

from flask import Blueprint, request

from app.middleware.auth_middleware import admin_only, current_user
from app.middleware.tenant_middleware import assert_owns_entity, assert_tenant_access, resolve_tenant_scope
from app.services import analytics_service, kb_service
from app.utils.response_utils import success

bp = Blueprint("analytics", __name__, url_prefix="/api/v1/analytics")


@bp.get("/dashboard")
@admin_only
def dashboard():
    scope = resolve_tenant_scope(current_user(), request.args.get("tenant_id"))
    return success(analytics_service.dashboard(scope))


@bp.get("/costs")
@admin_only
def costs():
    scope = resolve_tenant_scope(current_user(), request.args.get("tenant_id"))
    days = request.args.get("days", 30, type=int)
    return success(analytics_service.cost_breakdown(scope, days))


@bp.get("/tokens")
@admin_only
def tokens():
    scope = resolve_tenant_scope(current_user(), request.args.get("tenant_id"))
    days = request.args.get("days", 30, type=int)
    return success(analytics_service.token_breakdown(scope, days))


@bp.get("/tenant/<tenant_id>")
@admin_only
def tenant_analytics(tenant_id):
    assert_tenant_access(current_user(), tenant_id)
    return success({
        "dashboard": analytics_service.dashboard(tenant_id),
        "costs": analytics_service.cost_breakdown(tenant_id),
        "tokens": analytics_service.token_breakdown(tenant_id),
    })


@bp.get("/knowledge-base/<kb_id>")
@admin_only
def kb_analytics(kb_id):
    kb = kb_service.get_kb(kb_id)
    assert_owns_entity(current_user(), kb.tenant_id)
    scope = None if current_user().is_super_admin else current_user().tenant_id
    return success(analytics_service.kb_usage(scope, kb_id))
