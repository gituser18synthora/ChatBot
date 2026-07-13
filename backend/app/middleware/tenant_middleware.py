"""Tenant isolation guards.

The single place that answers: "may THIS user act on THIS tenant / KB / entity?"
Super Admin is cross-tenant; everyone else is locked to their own tenant_id.
The frontend never supplies a trusted tenant_id — it is always derived from the
authenticated user (or validated against it for Super Admin).
"""
from __future__ import annotations

from app.constants import Role
from app.models.user import User
from app.utils.response_utils import forbidden, not_found


def resolve_tenant_scope(user: User, requested_tenant_id: str | None) -> str | None:
    """Return the tenant_id the request should operate on.

    - Super Admin: may target any tenant; requested_tenant_id is honored (or
      None meaning "all tenants" for list endpoints).
    - Tenant Admin / Chat User: always their own tenant; a mismatching
      requested_tenant_id is rejected.
    """
    if user.role == Role.SUPER_ADMIN:
        return requested_tenant_id
    if requested_tenant_id and requested_tenant_id != user.tenant_id:
        raise forbidden("You do not have permission to access this tenant.")
    return user.tenant_id


def assert_tenant_access(user: User, tenant_id: str | None) -> None:
    """Raise if a non-super-admin user tries to touch another tenant."""
    if user.role == Role.SUPER_ADMIN:
        return
    if tenant_id is None or tenant_id != user.tenant_id:
        # 404 (not 403) to avoid confirming existence of other tenants' data.
        raise not_found()


def assert_owns_entity(user: User, entity_tenant_id: str) -> None:
    """Ensure the entity (KB, document, chat, ...) belongs to the user's tenant."""
    if user.role == Role.SUPER_ADMIN:
        return
    if entity_tenant_id != user.tenant_id:
        raise not_found()
