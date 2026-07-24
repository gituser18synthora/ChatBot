from __future__ import annotations

from datetime import datetime

from app.extensions import db
from app.models.base import GUID, TimestampMixin, uuid_pk


class AuthSession(TimestampMixin, db.Model):
    __tablename__ = "auth_sessions"

    id = uuid_pk()
    user_id = db.Column(GUID(), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = db.Column(db.String(80), nullable=False, index=True)
    user_agent = db.Column(db.String(400), nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)
    last_used_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    revoked_at = db.Column(db.DateTime, nullable=True, index=True)
    revoked_reason = db.Column(db.String(80), nullable=True)

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.expires_at > datetime.utcnow()


class RefreshToken(TimestampMixin, db.Model):
    __tablename__ = "refresh_tokens"

    id = uuid_pk()
    session_id = db.Column(GUID(), db.ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(GUID(), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    family_id = db.Column(GUID(), nullable=False, index=True)
    token_hash = db.Column(db.String(128), nullable=False, unique=True, index=True)
    jti_hash = db.Column(db.String(128), nullable=False, unique=True, index=True)
    parent_jti_hash = db.Column(db.String(128), nullable=True, index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    used_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True, index=True)
    revoked_reason = db.Column(db.String(80), nullable=True)

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.used_at is None and self.expires_at > datetime.utcnow()
