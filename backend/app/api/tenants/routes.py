from __future__ import annotations

from flask import Blueprint, request

from app.constants import Role
from app.middleware.auth_middleware import current_user, require_roles
from app.schemas import load_body
from app.schemas.tenant_schema import TenantCreateSchema, TenantUpdateSchema
from app.services import tenant_service
from app.utils.response_utils import paginated, success

bp = Blueprint("tenants", __name__, url_prefix="/api/v1/admin/tenants")


@bp.get("")
@require_roles(Role.SUPER_ADMIN)
def list_tenants():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    items, total = tenant_service.list_tenants(
        page, per_page, request.args.get("search"), request.args.get("status")
    )
    return paginated([t.to_dict() for t in items], page, per_page, total)


@bp.post("")
@require_roles(Role.SUPER_ADMIN)
def create_tenant():
    data = load_body(TenantCreateSchema())
    tenant, admin = tenant_service.create_tenant(data, current_user().id)
    body = tenant.to_dict()
    # Surface the created login so the UI can show/confirm the tenant's credentials.
    body["admin"] = {"id": admin.id, "name": admin.name, "email": admin.email} if admin else None
    return success(body, status=201)


@bp.get("/<tenant_id>")
@require_roles(Role.SUPER_ADMIN)
def get_tenant(tenant_id):
    return success(tenant_service.get_tenant(tenant_id).to_dict())


@bp.put("/<tenant_id>")
@require_roles(Role.SUPER_ADMIN)
def update_tenant(tenant_id):
    data = load_body(TenantUpdateSchema())
    return success(tenant_service.update_tenant(tenant_id, data, current_user().id).to_dict())


@bp.delete("/<tenant_id>")
@require_roles(Role.SUPER_ADMIN)
def delete_tenant(tenant_id):
    tenant_service.delete_tenant(tenant_id, current_user().id)
    return success({"message": "Tenant deleted."})
