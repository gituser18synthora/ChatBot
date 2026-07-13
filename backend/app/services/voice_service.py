"""TTS voice settings: platform defaults, tenant overrides, effective merge.

Priority (spec §3): tenant settings (only while the platform allows tenant
overrides) > platform defaults > built-in defaults. The chat client receives
one merged "effective" object and never reasons about levels itself.
"""
from __future__ import annotations

from app.constants import AuditAction
from app.extensions import db
from app.models.tenant import Tenant
from app.models.user import User
from app.models.voice_setting import VoiceSetting
from app.services import audit_service
from app.utils.response_utils import ApiError, not_found
from app.utils.uuid_utils import new_uuid

# Built-in defaults (spec priority level 3): the browser/device decides the
# voice; playback is on, auto-play off, neutral prosody.
BUILTIN_DEFAULTS = {
    "enabled": True,
    "provider": "browser",
    "voice_name": None,
    "language": None,
    "gender": None,
    "rate": 1.0,
    "pitch": 1.0,
    "volume": 1.0,
    "auto_play": False,
    "allow_tenant_override": True,
}

_UPDATABLE = (
    "enabled", "provider", "voice_name", "language", "gender",
    "rate", "pitch", "volume", "auto_play",
)


def _platform_row() -> VoiceSetting | None:
    return VoiceSetting.query.filter(VoiceSetting.tenant_id.is_(None)).first()


def _tenant_row(tenant_id: str) -> VoiceSetting | None:
    return VoiceSetting.query.filter_by(tenant_id=tenant_id).first()


def _as_dict(row: VoiceSetting | None) -> dict:
    """Row -> settings dict, backfilled with built-in defaults."""
    if row is None:
        return dict(BUILTIN_DEFAULTS)
    out = dict(BUILTIN_DEFAULTS)
    out.update({k: v for k, v in row.to_dict().items() if k in out})
    return out


def get_platform_settings() -> dict:
    return _as_dict(_platform_row())


def get_tenant_settings(tenant_id: str) -> dict:
    """The tenant's own row (for the Tenant Admin form), plus whether the
    platform currently lets it take effect."""
    platform = _as_dict(_platform_row())
    out = _as_dict(_tenant_row(tenant_id))
    out["allow_tenant_override"] = platform["allow_tenant_override"]
    out["configured"] = _tenant_row(tenant_id) is not None
    return out


def update_platform_settings(data: dict, actor: User) -> dict:
    row = _platform_row()
    if row is None:
        row = VoiceSetting(id=new_uuid(), tenant_id=None)
        db.session.add(row)
    old = row.to_dict()
    for field in _UPDATABLE + ("allow_tenant_override",):
        if field in data:
            setattr(row, field, data[field])
    row.updated_by = actor.id
    audit_service.log_action(
        action=AuditAction.VOICE_SETTINGS_UPDATED, entity_type="voice_settings",
        entity_id=row.id, tenant_id=None, user_id=actor.id,
        old_data=old, new_data=row.to_dict(), commit=False,
    )
    db.session.commit()
    return get_platform_settings()


def update_tenant_settings(tenant_id: str, data: dict, actor: User) -> dict:
    if not Tenant.query.get(tenant_id):
        raise not_found("The requested tenant was not found.")
    platform = _as_dict(_platform_row())
    if not platform["allow_tenant_override"]:
        raise ApiError(
            "Tenant-level voice settings are disabled by the platform administrator.",
            403,
            "voice_override_disabled",
        )
    row = _tenant_row(tenant_id)
    if row is None:
        row = VoiceSetting(id=new_uuid(), tenant_id=tenant_id)
        # New tenant rows start from the platform defaults so a partial update
        # never silently resets unrelated fields to built-ins.
        for field in _UPDATABLE:
            setattr(row, field, platform[field])
        db.session.add(row)
    old = row.to_dict()
    for field in _UPDATABLE:
        if field in data:
            setattr(row, field, data[field])
    row.updated_by = actor.id
    audit_service.log_action(
        action=AuditAction.VOICE_SETTINGS_UPDATED, entity_type="voice_settings",
        entity_id=row.id, tenant_id=tenant_id, user_id=actor.id,
        old_data=old, new_data=row.to_dict(), commit=False,
    )
    db.session.commit()
    return get_tenant_settings(tenant_id)


def reset_tenant_settings(tenant_id: str, actor: User) -> dict:
    """Remove the tenant row so the tenant follows platform defaults again."""
    row = _tenant_row(tenant_id)
    if row is not None:
        audit_service.log_action(
            action=AuditAction.VOICE_SETTINGS_UPDATED, entity_type="voice_settings",
            entity_id=row.id, tenant_id=tenant_id, user_id=actor.id,
            old_data=row.to_dict(), new_data=None, commit=False,
        )
        db.session.delete(row)
        db.session.commit()
    return get_tenant_settings(tenant_id)


def effective_settings(user: User) -> dict:
    """The merged settings the chat client should play audio with."""
    platform = _as_dict(_platform_row())
    settings = platform
    source = "platform" if _platform_row() is not None else "builtin"
    if user.tenant_id and platform["allow_tenant_override"]:
        tenant_row = _tenant_row(user.tenant_id)
        if tenant_row is not None:
            settings = _as_dict(tenant_row)
            source = "tenant"
    # Playback disabled globally wins over everything.
    if not platform["enabled"]:
        settings["enabled"] = False
    settings.pop("allow_tenant_override", None)
    settings["source"] = source
    return settings
