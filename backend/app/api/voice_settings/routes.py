"""TTS voice settings API.

- /api/v1/admin/voice-settings           GET/PUT  — platform defaults (Super Admin)
- /api/v1/admin/voice-settings/tenant    GET/PUT/DELETE — own tenant (Tenant Admin;
                                          writes rejected while overrides are off)
- /api/v1/voice-settings/effective       GET      — merged settings for the
                                          current user's chat playback (any role)
"""
from __future__ import annotations

from flask import Blueprint

from app.constants import Role
from app.middleware.auth_middleware import current_user, require_auth, require_roles
from app.schemas import load_body
from app.schemas.voice_schema import (
    PlatformVoiceSettingsUpdateSchema,
    VoiceSettingsUpdateSchema,
)
from app.services import voice_service
from app.utils.response_utils import success

bp = Blueprint("voice_settings", __name__, url_prefix="/api/v1")


@bp.get("/admin/voice-settings")
@require_roles(Role.SUPER_ADMIN)
def get_platform_voice_settings():
    return success(voice_service.get_platform_settings())


@bp.put("/admin/voice-settings")
@require_roles(Role.SUPER_ADMIN)
def update_platform_voice_settings():
    data = load_body(PlatformVoiceSettingsUpdateSchema())
    return success(voice_service.update_platform_settings(data, current_user()))


@bp.get("/admin/voice-settings/tenant")
@require_roles(Role.TENANT_ADMIN)
def get_tenant_voice_settings():
    return success(voice_service.get_tenant_settings(current_user().tenant_id))


@bp.put("/admin/voice-settings/tenant")
@require_roles(Role.TENANT_ADMIN)
def update_tenant_voice_settings():
    data = load_body(VoiceSettingsUpdateSchema())
    return success(voice_service.update_tenant_settings(current_user().tenant_id, data, current_user()))


@bp.delete("/admin/voice-settings/tenant")
@require_roles(Role.TENANT_ADMIN)
def reset_tenant_voice_settings():
    return success(voice_service.reset_tenant_settings(current_user().tenant_id, current_user()))


@bp.get("/voice-settings/effective")
@require_auth
def get_effective_voice_settings():
    return success(voice_service.effective_settings(current_user()))
