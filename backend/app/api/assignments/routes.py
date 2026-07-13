"""Super Tenant panel: share the Super Tenant's KBs with other tenants.

Super User (super_admin) only. The Super Tenant owns + ingests the KBs; these
endpoints grant/revoke other tenants' access to them.
"""
from __future__ import annotations

from flask import Blueprint, request

from app.constants import Role
from app.middleware.auth_middleware import current_user, require_roles
from app.schemas import load_body
from app.services import assignment_service, kb_service, tenant_service
from app.services.kb_service import _doc_count
from app.utils.response_utils import paginated, success, validation_error

bp = Blueprint("assignments", __name__, url_prefix="/api/v1/super-tenant")


@bp.get("")
@require_roles(Role.SUPER_ADMIN)
def super_tenant_info():
    st = tenant_service.get_super_tenant()
    return success({"super_tenant": st.to_dict() if st else None})


@bp.get("/knowledge-bases")
@require_roles(Role.SUPER_ADMIN)
def list_shareable_kbs():
    """The Super Tenant's KBs (the shareable library), with assignment counts."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    items, total, st = assignment_service.assignable_kbs(page, per_page, request.args.get("search"))
    if st is None:
        return success([], meta={"page": page, "per_page": per_page, "total": 0, "pages": 0,
                                 "no_super_tenant": True})
    data = []
    for kb in items:
        assignments = assignment_service.list_assignments(kb.id)
        d = kb.to_dict(document_count=_doc_count(kb.id))
        d["assigned_tenants"] = assignments
        data.append(d)
    return paginated(data, page, per_page, total)


@bp.get("/knowledge-bases/<kb_id>/assignments")
@require_roles(Role.SUPER_ADMIN)
def list_kb_assignments(kb_id):
    return success(assignment_service.list_assignments(kb_id))


@bp.post("/knowledge-bases/<kb_id>/assignments")
@require_roles(Role.SUPER_ADMIN)
def assign_kb(kb_id):
    body = request.get_json(silent=True) or {}
    tenant_id = body.get("tenant_id")
    if not tenant_id:
        raise validation_error("tenant_id is required.")
    assignment = assignment_service.assign(kb_id, tenant_id, current_user().id)
    return success(assignment.to_dict(), status=201)


@bp.delete("/knowledge-bases/<kb_id>/assignments/<tenant_id>")
@require_roles(Role.SUPER_ADMIN)
def unassign_kb(kb_id, tenant_id):
    assignment_service.unassign(kb_id, tenant_id, current_user().id)
    return success({"message": "Access revoked."})
