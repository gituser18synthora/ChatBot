"""Text-to-Speech voice settings.

One table serves both levels:
  - tenant_id NULL   -> the platform-wide defaults managed by the Super Admin
  - tenant_id set    -> a tenant's own settings managed by its Tenant Admin
                        (honored only while the platform row allows overrides)

The stored voice is a PREFERENCE (provider + voice name + language + gender),
not a guarantee: browser voices differ per device, so the client resolves the
closest available voice and falls back by language when the named voice does
not exist on the user's device.
"""
from __future__ import annotations

from app.extensions import db
from app.models.base import GUID, TimestampMixin, uuid_pk


class VoiceSetting(TimestampMixin, db.Model):
    __tablename__ = "voice_settings"

    id = uuid_pk()
    # NULL = platform defaults (exactly one such row); unique per tenant.
    tenant_id = db.Column(
        GUID(), db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True, unique=True, index=True,
    )
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    provider = db.Column(db.String(40), nullable=False, default="browser")
    voice_name = db.Column(db.String(200), nullable=True)
    language = db.Column(db.String(20), nullable=True)  # BCP-47, e.g. "hi-IN"
    gender = db.Column(db.String(10), nullable=True)  # male | female | neutral
    rate = db.Column(db.Float, nullable=False, default=1.0)  # 0.5 .. 2.0
    pitch = db.Column(db.Float, nullable=False, default=1.0)  # 0.0 .. 2.0
    volume = db.Column(db.Float, nullable=False, default=1.0)  # 0.0 .. 1.0
    auto_play = db.Column(db.Boolean, nullable=False, default=False)
    # Platform row only: may Tenant Admins configure their own voice settings?
    allow_tenant_override = db.Column(db.Boolean, nullable=False, default=True)
    updated_by = db.Column(GUID(), nullable=True)

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "enabled": self.enabled,
            "provider": self.provider,
            "voice_name": self.voice_name,
            "language": self.language,
            "gender": self.gender,
            "rate": self.rate,
            "pitch": self.pitch,
            "volume": self.volume,
            "auto_play": self.auto_play,
            "allow_tenant_override": self.allow_tenant_override,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
