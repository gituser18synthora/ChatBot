from __future__ import annotations

from flask import Blueprint, request

from app.constants import Role
from app.middleware.auth_middleware import admin_only, current_user
from app.middleware.tenant_middleware import assert_owns_entity, assert_tenant_access
from app.schemas import load_body
from app.schemas.kb_schema import KBCreateSchema, KBUpdateSchema
from app.services import kb_service
from app.utils.response_utils import paginated, success

bp = Blueprint("knowledge_bases", __name__, url_prefix="/api/v1")


@bp.get("/tenants/<tenant_id>/knowledge-bases")
@admin_only
def list_kbs(tenant_id):
    user = current_user()
    assert_tenant_access(user, tenant_id)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    items, total = kb_service.list_kbs(
        tenant_id, page, per_page, request.args.get("search"), request.args.get("status")
    )
    return paginated([kb_service.kb_payload(kb) for kb in items], page, per_page, total)


@bp.post("/tenants/<tenant_id>/knowledge-bases")
@admin_only
def create_kb(tenant_id):
    user = current_user()
    assert_tenant_access(user, tenant_id)
    data = load_body(KBCreateSchema())
    kb = kb_service.create_kb(tenant_id, data, user.id)
    return success(kb_service.kb_payload(kb), status=201)


@bp.get("/knowledge-bases/<kb_id>")
@admin_only
def get_kb(kb_id):
    kb = kb_service.get_kb(kb_id)
    assert_owns_entity(current_user(), kb.tenant_id)
    kb_service.refresh_kb_status(kb, commit=True)
    return success(kb_service.kb_payload(kb))


@bp.put("/knowledge-bases/<kb_id>")
@admin_only
def update_kb(kb_id):
    kb = kb_service.get_kb(kb_id)
    assert_owns_entity(current_user(), kb.tenant_id)
    data = load_body(KBUpdateSchema())
    return success(kb_service.kb_payload(kb_service.update_kb(kb_id, data, current_user().id)))


@bp.delete("/knowledge-bases/<kb_id>")
@admin_only
def delete_kb(kb_id):
    user = current_user()
    kb = kb_service.get_kb(kb_id)
    assert_owns_entity(user, kb.tenant_id)  # preserve existing authorization
    # Non-super-admins are additionally scoped to their own tenant inside the
    # service (defense in depth); Super Admin (None) may target any tenant.
    tenant_scope = None if user.role == Role.SUPER_ADMIN else user.tenant_id
    kb_service.delete_kb(kb_id, user.id, tenant_scope=tenant_scope)
    return success({"message": "Knowledge base deleted."})


@bp.get("/tenants/<tenant_id>/knowledge-bases/selectable")
@admin_only
def selectable_kbs(tenant_id):
    """KBs an admin may assign/select: the tenant's own active KBs plus KBs
    shared with the tenant by the Super Tenant. Tenant-scoped."""
    user = current_user()
    assert_tenant_access(user, tenant_id)
    from app.services import assignment_service
    kbs = assignment_service.selectable_kbs_for_tenant(tenant_id)
    owned = {kb.id for kb in kbs if kb.tenant_id == tenant_id}
    return success([
        {
            "id": kb.id,
            "kb_name": kb.kb_name,
            "shared": kb.id not in owned,
            "status": kb.status,
            "status_message": kb.status_message,
            "ready": kb.status == "ready",
        }
        for kb in kbs
    ])
