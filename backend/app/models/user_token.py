"""Per-chat-user access tokens issued by Tenant Admins.

One row per Chat User. Regenerating replaces the previous token. The row stores
a short opaque token plus the user's tenant_id, KB scope, and user_id so
embed/API clients can authenticate as that Chat User against those KBs.
"""
from __future__ import annotations

from app.extensions import db
from app.models.base import GUID, TimestampMixin, uuid_pk


class UserToken(TimestampMixin, db.Model):
    __tablename__ = "user_token"

    id = uuid_pk()
    user_id = db.Column(
        GUID(), db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    tenant_id = db.Column(
        GUID(), db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Snapshot of KB ids the token is scoped to at generation time.
    kb_ids = db.Column(db.JSON, nullable=False, default=list)
    token = db.Column(db.Text, nullable=False, unique=True, index=True)
    created_by = db.Column(GUID(), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "kb_ids": list(self.kb_ids or []),
            "token": self.token,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
