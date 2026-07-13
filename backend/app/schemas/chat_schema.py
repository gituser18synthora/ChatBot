from __future__ import annotations

from marshmallow import Schema, fields, validate


class SessionCreateSchema(Schema):
    title = fields.Str(load_default=None, allow_none=True, validate=validate.Length(max=500))
    kb_ids = fields.List(fields.Str(), load_default=list)


class SessionUpdateSchema(Schema):
    title = fields.Str(required=True, validate=validate.Length(min=1, max=500))


class MessageCreateSchema(Schema):
    message = fields.Str(required=True, validate=validate.Length(min=1, max=8000))
