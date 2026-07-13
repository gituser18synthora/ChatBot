"""Tenant CRUD with audit logging."""
from __future__ import annotations

import re
import secrets

from sqlalchemy.exc import IntegrityError

from app.constants import AuditAction, Role, TenantStatus
from app.extensions import db
from app.models.tenant import Tenant
from app.models.user import User
from app.services import audit_service
from app.utils.response_utils import conflict, not_found, validation_error


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug[:60] or "tenant"


def generate_tenant_code(name: str) -> str:
    """Derive a unique, URL-safe tenant code from the name.

    Tries the plain slug, then slug-2, slug-3, …; falls back to a random suffix
    if the name collides many times. Guaranteed unique against existing rows.
    """
    base = _slugify(name)
    if not Tenant.query.filter_by(tenant_code=base).first():
        return base
    for i in range(2, 100):
        candidate = f"{base}-{i}"
        if not Tenant.query.filter_by(tenant_code=candidate).first():
            return candidate
    return f"{base}-{secrets.token_hex(3)}"


def list_tenants(page: int, per_page: int, search: str | None = None, status: str | None = None):
    q = Tenant.query.filter(Tenant.deleted_at.is_(None))
    if search:
        like = f"%{search}%"
        q = q.filter(db.or_(Tenant.tenant_name.ilike(like), Tenant.tenant_code.ilike(like)))
    if status:
        q = q.filter(Tenant.status == status)
    q = q.order_by(Tenant.created_at.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return items, total


def get_tenant(tenant_id: str) -> Tenant:
    tenant = Tenant.query.get(tenant_id)
    if not tenant or tenant.deleted_at is not None:
        raise not_found("The requested tenant was not found.")
    return tenant


def get_super_tenant() -> Tenant | None:
    return Tenant.query.filter_by(is_super_tenant=True).first()


def _clear_other_super_tenants(except_id: str | None = None) -> None:
    """Enforce a single Super Tenant."""
    q = Tenant.query.filter(Tenant.is_super_tenant.is_(True))
    if except_id:
        q = q.filter(Tenant.id != except_id)
    for t in q.all():
        t.is_super_tenant = False


def create_tenant(data: dict, actor_id: str) -> tuple[Tenant, User | None]:
    """Create a tenant and, when admin credentials are supplied, its login.

    A tenant is meant to be able to log in, so the API always sends an
    `admin_email` + `admin_password`; we create a Tenant Admin user bound to the
    new tenant. The pair is optional at this layer (seed scripts / tests may omit
    it), in which case no login is created. Returns (tenant, admin_user|None).
    """
    admin_email = (data.get("admin_email") or "").strip().lower()
    admin_password = data.get("admin_password") or ""
    admin_name = (data.get("admin_name") or "").strip() or "Tenant Admin"

    # Reject a duplicate admin email up front so we never create the tenant and
    # then fail to attach its login (which would leave a loginless tenant).
    if admin_email:
        if not admin_password or len(admin_password) < 8:
            raise validation_error("The tenant admin password must be at least 8 characters.")
        if User.query.filter_by(email=admin_email).first():
            raise conflict("A user with this admin email already exists. Please use a different email.")

    # Auto-generate the tenant code when the caller doesn't supply one.
    supplied = (data.get("tenant_code") or "").strip()
    tenant_code = supplied or generate_tenant_code(data["tenant_name"])
    is_super = bool(data.get("is_super_tenant", False))
    if is_super:
        _clear_other_super_tenants()
    tenant = Tenant(
        tenant_name=data["tenant_name"],
        tenant_code=tenant_code,
        status=data.get("status", TenantStatus.ACTIVE),
        is_super_tenant=is_super,
        contact_name=data.get("contact_name"),
        contact_email=data.get("contact_email"),
    )
    db.session.add(tenant)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise conflict("A tenant with this code already exists. Please use a different code.")

    audit_service.log_action(
        action=AuditAction.TENANT_CREATED, entity_type="tenant", entity_id=tenant.id,
        tenant_id=tenant.id, user_id=actor_id, new_data=tenant.to_dict(), commit=False,
    )

    admin: User | None = None
    if admin_email:
        admin = User(
            tenant_id=tenant.id, name=admin_name, email=admin_email,
            role=Role.TENANT_ADMIN, is_active=True,
        )
        admin.set_password(admin_password)
        db.session.add(admin)
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            raise conflict("A user with this admin email already exists. Please use a different email.")
        audit_service.log_action(
            action=AuditAction.USER_CREATED, entity_type="user", entity_id=admin.id,
            tenant_id=tenant.id, user_id=actor_id, new_data=admin.to_dict(), commit=False,
        )

    db.session.commit()
    return tenant, admin


def update_own_tenant(user: User, data: dict) -> Tenant:
    """A Tenant Admin updates their own tenant profile (name, contact, and the
    chatbot answering mode).

    Cannot change status or Super Tenant designation — those are Super User only.
    """
    if not user.tenant_id:
        raise validation_error("Your account is not attached to a tenant.")
    tenant = get_tenant(user.tenant_id)
    old = tenant.to_dict()
    for field in ("tenant_name", "contact_name", "contact_email", "rag_mode"):
        if field in data and data[field] is not None:
            setattr(tenant, field, data[field])
    audit_service.log_action(
        action=AuditAction.PROFILE_UPDATED, entity_type="tenant", entity_id=tenant.id,
        tenant_id=tenant.id, user_id=user.id, old_data=old, new_data=tenant.to_dict(), commit=False,
    )
    db.session.commit()
    return tenant


def update_tenant(tenant_id: str, data: dict, actor_id: str) -> Tenant:
    tenant = get_tenant(tenant_id)
    old = tenant.to_dict()
    for field in ("tenant_name", "contact_name", "contact_email", "status", "rag_mode"):
        if field in data and data[field] is not None:
            setattr(tenant, field, data[field])
    if "is_super_tenant" in data and data["is_super_tenant"] is not None:
        if data["is_super_tenant"]:
            _clear_other_super_tenants(except_id=tenant.id)
        tenant.is_super_tenant = bool(data["is_super_tenant"])

    action = AuditAction.TENANT_UPDATED
    if data.get("status") == TenantStatus.INACTIVE and old["status"] != TenantStatus.INACTIVE:
        action = AuditAction.TENANT_DEACTIVATED

    audit_service.log_action(
        action=action, entity_type="tenant", entity_id=tenant.id,
        tenant_id=tenant.id, user_id=actor_id, old_data=old, new_data=tenant.to_dict(), commit=False,
    )
    db.session.commit()
    return tenant


def delete_tenant(tenant_id: str, actor_id: str) -> None:
    """Soft-delete: the tenant and all its data are RETAINED for audit/reference.
    The tenant is archived (deleted_at set, status inactive), removed from active
    lists, and its users are deactivated so they can no longer log in."""
    from datetime import datetime

    from app.models.user import User

    tenant = get_tenant(tenant_id)
    old = tenant.to_dict()
    now = datetime.utcnow()
    tenant.deleted_at = now
    tenant.status = TenantStatus.INACTIVE
    tenant.is_super_tenant = False

    # Deactivate the tenant's users so they cannot authenticate. Records are kept.
    User.query.filter(User.tenant_id == tenant_id, User.deleted_at.is_(None)).update(
        {User.is_active: False}, synchronize_session=False
    )

    audit_service.log_action(
        action=AuditAction.TENANT_DELETED, entity_type="tenant", entity_id=tenant_id,
        tenant_id=tenant_id, user_id=actor_id, old_data=old, new_data=tenant.to_dict(), commit=False,
    )
    db.session.commit()
