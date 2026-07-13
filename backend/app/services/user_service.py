"""User management with role + tenant constraints."""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.constants import AuditAction, Role
from app.extensions import db
from app.models.user import User
from app.services import audit_service
from app.utils.response_utils import ApiError, conflict, forbidden, not_found, validation_error


def list_users(tenant_id: str | None, page: int, per_page: int, search: str | None = None, role: str | None = None):
    q = User.query.filter(User.deleted_at.is_(None))
    if tenant_id is not None:
        q = q.filter(User.tenant_id == tenant_id)
    if search:
        like = f"%{search}%"
        q = q.filter(db.or_(User.name.ilike(like), User.email.ilike(like)))
    if role:
        q = q.filter(User.role == role)
    q = q.order_by(User.created_at.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return items, total


def get_user(user_id: str) -> User:
    user = User.query.get(user_id)
    if not user or user.deleted_at is not None:
        raise not_found("The requested user was not found.")
    return user


def _validate_role_creation(actor: User, new_role: str, target_tenant_id: str | None) -> None:
    if new_role not in Role.ALL:
        raise validation_error("Invalid role.")
    if actor.role == Role.SUPER_ADMIN:
        if new_role != Role.SUPER_ADMIN and not target_tenant_id:
            raise validation_error("A tenant is required for tenant admins and chat users.")
        return
    # Tenant Admin: may ONLY create Chat Users, and only within their own tenant.
    if new_role != Role.CHAT_USER:
        raise forbidden("Tenant Admins can only create Chat Users.")
    if target_tenant_id != actor.tenant_id:
        raise forbidden("You can only create users within your own tenant.")


def create_user(actor: User, data: dict) -> User:
    role = data["role"]
    tenant_id = None if role == Role.SUPER_ADMIN else (
        data.get("tenant_id") if actor.role == Role.SUPER_ADMIN else actor.tenant_id
    )
    _validate_role_creation(actor, role, tenant_id)

    # Optional initial KB scoping, validated BEFORE the user row is created so a
    # bad selection never leaves a half-configured account. Scoping applies to
    # Chat Users only; empty means the Chat User searches all tenant KBs.
    kb_ids = list(dict.fromkeys(data.get("kb_ids") or []))
    if kb_ids:
        if role != Role.CHAT_USER:
            raise validation_error(
                "Knowledge Base assignment is only available for Chat Users. "
                "Tenant Admins always use all tenant Knowledge Bases."
            )
        if not tenant_id:
            raise validation_error("Knowledge base access can only be scoped for tenant users.")
        from app.services import assignment_service

        selectable = {kb.id for kb in assignment_service.selectable_kbs_for_tenant(tenant_id)}
        if any(k not in selectable for k in kb_ids):
            raise forbidden("One or more selected knowledge bases are not available to this tenant.")

    user = User(
        tenant_id=tenant_id,
        name=data["name"],
        email=data["email"].strip().lower(),
        role=role,
        is_active=data.get("is_active", True),
    )
    user.set_password(data["password"])
    db.session.add(user)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise conflict("A user with this email already exists.")

    audit_service.log_action(
        action=AuditAction.USER_CREATED, entity_type="user", entity_id=user.id,
        tenant_id=tenant_id, user_id=actor.id, new_data=user.to_dict(), commit=False,
    )

    if kb_ids:
        from app.models.user_kb_assignment import UserKnowledgeBaseAssignment
        from app.utils.uuid_utils import new_uuid

        for kb_id in kb_ids:
            db.session.add(UserKnowledgeBaseAssignment(
                id=new_uuid(), user_id=user.id, kb_id=kb_id, assigned_by=actor.id,
            ))
        audit_service.log_action(
            action=AuditAction.USER_KB_ASSIGNED, entity_type="user", entity_id=user.id,
            tenant_id=tenant_id, user_id=actor.id, new_data={"kb_ids": kb_ids}, commit=False,
        )

    db.session.commit()
    return user


def update_user(actor: User, user_id: str, data: dict) -> User:
    user = get_user(user_id)
    if actor.role != Role.SUPER_ADMIN and user.tenant_id != actor.tenant_id:
        raise not_found("The requested user was not found.")
    old = user.to_dict()
    if "name" in data and data["name"]:
        user.name = data["name"]
    if "password" in data and data["password"]:
        user.set_password(data["password"])
    if "role" in data and data["role"] and actor.role == Role.SUPER_ADMIN:
        user.role = data["role"]

    audit_service.log_action(
        action=AuditAction.USER_UPDATED, entity_type="user", entity_id=user.id,
        tenant_id=user.tenant_id, user_id=actor.id, old_data=old, new_data=user.to_dict(), commit=False,
    )
    db.session.commit()
    return user


def set_status(actor: User, user_id: str, is_active: bool) -> User:
    user = get_user(user_id)
    if actor.role != Role.SUPER_ADMIN and user.tenant_id != actor.tenant_id:
        raise not_found("The requested user was not found.")
    if user.id == actor.id:
        raise ApiError("You cannot change your own account status.", 400, "self_status_change")
    old = user.to_dict()
    user.is_active = is_active
    audit_service.log_action(
        action=AuditAction.USER_DISABLED if not is_active else AuditAction.USER_UPDATED,
        entity_type="user", entity_id=user.id, tenant_id=user.tenant_id,
        user_id=actor.id, old_data=old, new_data=user.to_dict(), commit=False,
    )
    db.session.commit()
    return user


def delete_user(actor: User, user_id: str) -> User:
    """Soft-delete a user: the record is RETAINED for audit; the account is
    deactivated and excluded from lists. Login is blocked (is_active=False).

    Permissions: a Super User may delete anyone (except self); a Tenant Admin may
    delete only Chat Users in their own tenant (mirrors the creation rule)."""
    from datetime import datetime

    user = get_user(user_id)
    if user.id == actor.id:
        raise ApiError("You cannot delete your own account.", 400, "self_delete")

    if actor.role != Role.SUPER_ADMIN:
        if user.tenant_id != actor.tenant_id:
            raise not_found("The requested user was not found.")
        if user.role != Role.CHAT_USER:
            raise forbidden("Tenant Admins can only delete Chat Users.")

    old = user.to_dict()
    user.deleted_at = datetime.utcnow()
    user.is_active = False
    audit_service.log_action(
        action=AuditAction.USER_DISABLED, entity_type="user", entity_id=user.id,
        tenant_id=user.tenant_id, user_id=actor.id, old_data=old, new_data=user.to_dict(), commit=False,
    )
    db.session.commit()
    return user
