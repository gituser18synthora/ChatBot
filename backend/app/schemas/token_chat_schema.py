"""Token-authenticated chat (opaque Chat User access token).

Separate from the JWT chat flow. Frontend sends session_id + query in the body
and the generated access token in the `X-Access-Token` header (not the body).
"""
from __future__ import annotations

from marshmallow import Schema, fields, validate


class TokenChatSchema(Schema):
    session_id = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    query = fields.Str(required=True, validate=validate.Length(min=1, max=8000))
