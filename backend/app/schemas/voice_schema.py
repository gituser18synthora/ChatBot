"""Validation for TTS voice settings.

Ranges mirror the Web Speech API contract (and are re-checked in the frontend
form): rate 0.5–2.0, pitch 0.0–2.0, volume 0.0–1.0.
"""
from __future__ import annotations

from marshmallow import Schema, fields, validate

VOICE_GENDERS = {"male", "female", "neutral"}
VOICE_PROVIDERS = {"browser"}  # extensible: cloud TTS providers plug in here

_locale = validate.Regexp(
    r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$",
    error="Use a BCP-47 code such as 'en', 'hi-IN' or 'mr-IN'.",
)


class VoiceSettingsUpdateSchema(Schema):
    enabled = fields.Bool()
    provider = fields.Str(validate=validate.OneOf(VOICE_PROVIDERS))
    voice_name = fields.Str(allow_none=True, validate=validate.Length(max=200))
    language = fields.Str(allow_none=True, validate=_locale)
    gender = fields.Str(allow_none=True, validate=validate.OneOf(VOICE_GENDERS))
    rate = fields.Float(validate=validate.Range(min=0.5, max=2.0))
    pitch = fields.Float(validate=validate.Range(min=0.0, max=2.0))
    volume = fields.Float(validate=validate.Range(min=0.0, max=1.0))
    auto_play = fields.Bool()


class PlatformVoiceSettingsUpdateSchema(VoiceSettingsUpdateSchema):
    """Platform (Super Admin) row additionally controls tenant overrides."""
    allow_tenant_override = fields.Bool()
