"""Token-authenticated chat (opaque Chat User access token).

Separate from the JWT chat flow. Frontend sends the generated user_token value
plus a session_id and query; we authorize via the `user_token` table and run
KMRAG retrieval with the stored tenant_id / kb_ids / user_id.
"""
from __future__ import annotations

from marshmallow import Schema, fields, validate


class TokenChatSchema(Schema):
    token = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    session_id = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    query = fields.Str(required=True, validate=validate.Length(min=1, max=8000))
