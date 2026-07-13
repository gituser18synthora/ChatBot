from __future__ import annotations

from marshmallow import Schema, fields, validate

from app.constants import KBStatus


class KBCreateSchema(Schema):
    # Optional explicit globally-unique kb_id; generated if omitted.
    id = fields.Str(load_default=None, allow_none=True)
    kb_name = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    description = fields.Str(load_default=None, allow_none=True)
    # Creation always starts lifecycle-managed as pending unless explicitly
    # created inactive. `active` is accepted for old clients and normalized.
    status = fields.Str(load_default=None, allow_none=True, validate=validate.OneOf(KBStatus.INPUT_VALUES))


class KBUpdateSchema(Schema):
    kb_name = fields.Str(validate=validate.Length(min=1, max=200))
    description = fields.Str(allow_none=True)
    # Status is lifecycle-managed; updates only use this to disable or re-enable.
    status = fields.Str(validate=validate.OneOf(KBStatus.INPUT_VALUES))
