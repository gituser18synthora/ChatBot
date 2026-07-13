from __future__ import annotations

from marshmallow import Schema, fields, validate

from app.constants import Role


class UserCreateSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=8, max=200))
    role = fields.Str(required=True, validate=validate.OneOf(Role.ALL))
    tenant_id = fields.Str(load_default=None, allow_none=True)
    is_active = fields.Bool(load_default=True)
    # Optional initial KB scoping (chat access). For Chat Users, empty/omitted
    # means no KB access; for Tenant Admins, it means all tenant KBs.
    # Ignored for super admins.
    kb_ids = fields.List(fields.Str(), load_default=list)


class UserUpdateSchema(Schema):
    name = fields.Str(validate=validate.Length(min=1, max=200))
    password = fields.Str(validate=validate.Length(min=8, max=200))
    role = fields.Str(validate=validate.OneOf(Role.ALL))


class UserStatusSchema(Schema):
    is_active = fields.Bool(required=True)


class UserKbAssignSchema(Schema):
    # The full desired set of KB ids for this user. Empty removes Chat User KB
    # access; Tenant Admins with no explicit scope use all tenant KBs.
    kb_ids = fields.List(fields.Str(), load_default=list)
