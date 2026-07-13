from __future__ import annotations

from flask import Blueprint, request

from app.constants import Role
from app.middleware.auth_middleware import admin_only, current_user
from app.middleware.tenant_middleware import resolve_tenant_scope
from app.schemas import load_body
from app.schemas.user_schema import (
    UserCreateSchema,
    UserKbAssignSchema,
    UserStatusSchema,
    UserUpdateSchema,
)
from app.services import user_kb_service, user_service
from app.utils.response_utils import paginated, success

bp = Blueprint("users", __name__, url_prefix="/api/v1/users")


@bp.get("")
@admin_only
def list_users():
    user = current_user()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    # Super Admin may pass ?tenant_id=; tenant admins are locked to their tenant.
    scope = resolve_tenant_scope(user, request.args.get("tenant_id"))
    items, total = user_service.list_users(
        scope, page, per_page, request.args.get("search"), request.args.get("role")
    )
    return paginated([u.to_dict() for u in items], page, per_page, total)


@bp.post("")
@admin_only
def create_user():
    data = load_body(UserCreateSchema())
    created = user_service.create_user(current_user(), data)
    return success(created.to_dict(), status=201)


@bp.get("/<user_id>")
@admin_only
def get_user(user_id):
    user = current_user()
    target = user_service.get_user(user_id)
    if user.role != Role.SUPER_ADMIN and target.tenant_id != user.tenant_id:
        from app.utils.response_utils import not_found
        raise not_found("The requested user was not found.")
    return success(target.to_dict())


@bp.put("/<user_id>")
@admin_only
def update_user(user_id):
    data = load_body(UserUpdateSchema())
    return success(user_service.update_user(current_user(), user_id, data).to_dict())


@bp.patch("/<user_id>/status")
@admin_only
def set_status(user_id):
    data = load_body(UserStatusSchema())
    return success(user_service.set_status(current_user(), user_id, data["is_active"]).to_dict())


@bp.delete("/<user_id>")
@admin_only
def delete_user(user_id):
    user_service.delete_user(current_user(), user_id)
    return success({"message": "User deleted. The record is retained for audit."})


# ── Per-user Knowledge Base scoping ───────────────────────────
@bp.get("/<user_id>/knowledge-bases")
@admin_only
def get_user_kbs(user_id):
    return success(user_kb_service.get_user_kb_access(current_user(), user_id))


@bp.put("/<user_id>/knowledge-bases")
@admin_only
def set_user_kbs(user_id):
    data = load_body(UserKbAssignSchema())
    return success(user_kb_service.set_user_kbs(current_user(), user_id, data["kb_ids"]))
