from __future__ import annotations

from marshmallow import Schema, fields, validate

from app.constants import RagMode, TenantStatus


class TenantCreateSchema(Schema):
    tenant_name = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    # Optional: the system generates a unique code from the name when omitted.
    tenant_code = fields.Str(load_default=None, allow_none=True, validate=validate.Length(max=80))
    status = fields.Str(load_default=TenantStatus.ACTIVE, validate=validate.OneOf(TenantStatus.ALL))
    # `is_super_tenant` is deliberately NOT accepted here: every tenant is created
    # as a normal tenant. The single Super Tenant (owner of the shared KB library)
    # is designated afterwards by a Super User via tenant update.
    contact_name = fields.Str(load_default=None, allow_none=True)
    contact_email = fields.Email(load_default=None, allow_none=True)
    # Tenant login. Supplied by the console so a new tenant can sign in; a Tenant
    # Admin user is created from these. Optional at the schema level for
    # seed/import callers, but the UI always sends them.
    admin_name = fields.Str(load_default=None, allow_none=True, validate=validate.Length(max=200))
    admin_email = fields.Email(load_default=None, allow_none=True)
    admin_password = fields.Str(load_default=None, allow_none=True, validate=validate.Length(min=8, max=200))


class TenantUpdateSchema(Schema):
    tenant_name = fields.Str(validate=validate.Length(min=1, max=200))
    status = fields.Str(validate=validate.OneOf(TenantStatus.ALL))
    is_super_tenant = fields.Bool()
    rag_mode = fields.Str(validate=validate.OneOf(RagMode.ALL))
    contact_name = fields.Str(allow_none=True)
    contact_email = fields.Email(allow_none=True)


class TenantProfileUpdateSchema(Schema):
    """Self-service fields a Tenant Admin may change on their own tenant."""
    tenant_name = fields.Str(validate=validate.Length(min=1, max=200))
    rag_mode = fields.Str(validate=validate.OneOf(RagMode.ALL))
    contact_name = fields.Str(allow_none=True)
    contact_email = fields.Email(allow_none=True)


class PasswordChangeSchema(Schema):
    current_password = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    new_password = fields.Str(required=True, validate=validate.Length(min=8, max=200))
