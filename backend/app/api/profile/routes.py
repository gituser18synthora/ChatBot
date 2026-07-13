"""Self-service profile: the signed-in user's own account and tenant.

  GET  /api/v1/profile           -> current user + their tenant (if any)
  PUT  /api/v1/profile/tenant    -> Tenant Admin updates their own tenant
  PUT  /api/v1/profile/password  -> any user changes their own password

Everything here is scoped to `current_user()` — no tenant_id is ever accepted
from the client, so a user can only ever read/update their own profile.
"""
from __future__ import annotations

from flask import Blueprint

from app.constants import Role
from app.middleware.auth_middleware import current_user, require_auth, require_roles
from app.schemas import load_body
from app.schemas.tenant_schema import PasswordChangeSchema, TenantProfileUpdateSchema
from app.services import auth_service, tenant_service
from app.utils.response_utils import success

bp = Blueprint("profile", __name__, url_prefix="/api/v1/profile")


@bp.get("")
@require_auth
def get_profile():
    user = current_user()
    tenant = None
    if user.tenant_id:
        tenant = tenant_service.get_tenant(user.tenant_id).to_dict()
    return success({"user": user.to_dict(), "tenant": tenant})


@bp.put("/tenant")
@require_roles(Role.TENANT_ADMIN)
def update_tenant_profile():
    data = load_body(TenantProfileUpdateSchema())
    tenant = tenant_service.update_own_tenant(current_user(), data)
    return success(tenant.to_dict())


@bp.put("/password")
@require_auth
def change_password():
    data = load_body(PasswordChangeSchema())
    auth_service.change_password(current_user(), data["current_password"], data["new_password"])
    return success({"message": "Password updated."})
