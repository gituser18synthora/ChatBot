from __future__ import annotations

from datetime import datetime

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.constants import Role
from app.extensions import db
from app.models.base import GUID, TimestampMixin, uuid_pk

_ph = PasswordHasher()


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id = uuid_pk()
    # NULL tenant_id => Super Admin (platform-wide).
    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime, nullable=True)
    failed_login_count = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    # Soft delete: retained for audit; excluded from lists and blocked from login.
    deleted_at = db.Column(db.DateTime, nullable=True)

    # ── Password handling (argon2) ────────────────────────────
    def set_password(self, plain: str) -> None:
        self.password_hash = _ph.hash(plain)

    def check_password(self, plain: str) -> bool:
        try:
            return _ph.verify(self.password_hash, plain)
        except (VerifyMismatchError, Exception):
            return False

    # ── Role helpers ──────────────────────────────────────────
    @property
    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > datetime.utcnow())

    @property
    def is_super_admin(self) -> bool:
        return self.role == Role.SUPER_ADMIN

    @property
    def is_tenant_admin(self) -> bool:
        return self.role == Role.TENANT_ADMIN

    @property
    def is_admin(self) -> bool:
        return self.role in Role.ADMINS

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "locked_until": self.locked_until.isoformat() if self.locked_until else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
