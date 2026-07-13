from __future__ import annotations

from marshmallow import Schema, fields, validate


class PaginationSchema(Schema):
    page = fields.Int(load_default=1, validate=validate.Range(min=1))
    per_page = fields.Int(load_default=20, validate=validate.Range(min=1, max=100))
    search = fields.Str(load_default=None, allow_none=True)
    status = fields.Str(load_default=None, allow_none=True)
