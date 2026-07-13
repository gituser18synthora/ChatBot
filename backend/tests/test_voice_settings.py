"""TTS voice settings: role gating, validation, override control, and the
tenant > platform > builtin effective-resolution priority."""

PLATFORM = "/api/v1/admin/voice-settings"
TENANT = "/api/v1/admin/voice-settings/tenant"
EFFECTIVE = "/api/v1/voice-settings/effective"


# ── Role gating ───────────────────────────────────────────────
def test_platform_settings_super_admin_only(client, auth, seed):
    for email in ("admin_a@x.com", "user_a@x.com"):
        assert client.get(PLATFORM, headers=auth(email)).status_code == 403
        assert client.put(PLATFORM, headers=auth(email), json={"rate": 1.5}).status_code == 403
    assert client.get(PLATFORM, headers=auth("root@x.com")).status_code == 200


def test_tenant_settings_tenant_admin_only(client, auth, seed):
    assert client.get(TENANT, headers=auth("user_a@x.com")).status_code == 403
    assert client.get(TENANT, headers=auth("root@x.com")).status_code == 403
    assert client.get(TENANT, headers=auth("admin_a@x.com")).status_code == 200


def test_effective_settings_any_authenticated_role(client, auth, seed):
    for email in ("user_a@x.com", "admin_a@x.com", "root@x.com"):
        r = client.get(EFFECTIVE, headers=auth(email))
        assert r.status_code == 200
        data = r.get_json()["data"]
        assert data["enabled"] is True  # builtin defaults before any config
        assert data["rate"] == 1.0
        assert data["source"] == "builtin"
        assert "allow_tenant_override" not in data  # internal knob, not client-facing


# ── Validation (backend side of the double validation) ───────
def test_rate_pitch_volume_bounds_rejected(client, auth, seed):
    h = auth("root@x.com")
    for payload in (
        {"rate": 0.4}, {"rate": 2.5},
        {"pitch": -0.1}, {"pitch": 2.1},
        {"volume": -0.1}, {"volume": 1.1},
        {"gender": "robot"},
        {"language": "not a locale"},
        {"provider": "elevenlabs"},  # not an enabled provider
    ):
        r = client.put(PLATFORM, headers=h, json=payload)
        assert r.status_code == 422, payload


def test_valid_update_persists_to_db(client, auth, seed):
    h = auth("root@x.com")
    r = client.put(PLATFORM, headers=h, json={
        "rate": 1.25, "pitch": 1.1, "volume": 0.8, "language": "hi-IN",
        "gender": "female", "voice_name": "Google हिन्दी", "auto_play": True,
    })
    assert r.status_code == 200
    # DB-persisted (not client state): a fresh GET returns the saved values.
    data = client.get(PLATFORM, headers=h).get_json()["data"]
    assert data["rate"] == 1.25
    assert data["language"] == "hi-IN"
    assert data["gender"] == "female"
    assert data["voice_name"] == "Google हिन्दी"
    assert data["auto_play"] is True
    from app.models.voice_setting import VoiceSetting
    row = VoiceSetting.query.filter(VoiceSetting.tenant_id.is_(None)).one()
    assert row.rate == 1.25


# ── Tenant override control ───────────────────────────────────
def test_tenant_update_blocked_when_override_disabled(client, auth, seed):
    client.put(PLATFORM, headers=auth("root@x.com"), json={"allow_tenant_override": False})
    r = client.put(TENANT, headers=auth("admin_a@x.com"), json={"rate": 1.5})
    assert r.status_code == 403
    assert r.get_json()["error"]["code"] == "voice_override_disabled"
    # The GET still works so the form can show WHY it is locked.
    data = client.get(TENANT, headers=auth("admin_a@x.com")).get_json()["data"]
    assert data["allow_tenant_override"] is False


def test_tenant_row_starts_from_platform_defaults(client, auth, seed):
    # Platform sets hi-IN @ 1.5x; tenant admin changes ONLY the volume. The
    # tenant row must inherit the platform values, not reset to builtins.
    client.put(PLATFORM, headers=auth("root@x.com"),
               json={"language": "hi-IN", "rate": 1.5})
    data = client.put(TENANT, headers=auth("admin_a@x.com"),
                      json={"volume": 0.5}).get_json()["data"]
    assert data["language"] == "hi-IN"
    assert data["rate"] == 1.5
    assert data["volume"] == 0.5


# ── Effective resolution priority ─────────────────────────────
def test_effective_priority_tenant_over_platform_over_builtin(client, auth, seed):
    chat_user = auth("user_a@x.com")

    # 1) Nothing configured -> builtins.
    assert client.get(EFFECTIVE, headers=chat_user).get_json()["data"]["source"] == "builtin"

    # 2) Platform configured -> platform.
    client.put(PLATFORM, headers=auth("root@x.com"), json={"rate": 1.25, "language": "en-IN"})
    data = client.get(EFFECTIVE, headers=chat_user).get_json()["data"]
    assert (data["source"], data["rate"], data["language"]) == ("platform", 1.25, "en-IN")

    # 3) Tenant configured -> tenant wins for that tenant's users.
    client.put(TENANT, headers=auth("admin_a@x.com"), json={"rate": 0.75, "language": "mr-IN"})
    data = client.get(EFFECTIVE, headers=chat_user).get_json()["data"]
    assert (data["source"], data["rate"], data["language"]) == ("tenant", 0.75, "mr-IN")

    # 4) Overrides turned off -> the tenant row stops applying immediately.
    client.put(PLATFORM, headers=auth("root@x.com"), json={"allow_tenant_override": False})
    data = client.get(EFFECTIVE, headers=chat_user).get_json()["data"]
    assert (data["source"], data["rate"]) == ("platform", 1.25)

    # 5) Tenant reset (after re-enabling) -> back to platform defaults.
    client.put(PLATFORM, headers=auth("root@x.com"), json={"allow_tenant_override": True})
    client.delete(TENANT, headers=auth("admin_a@x.com"))
    data = client.get(EFFECTIVE, headers=chat_user).get_json()["data"]
    assert data["source"] == "platform"


def test_global_disable_wins_over_tenant_enabled(client, auth, seed):
    client.put(TENANT, headers=auth("admin_a@x.com"), json={"enabled": True})
    client.put(PLATFORM, headers=auth("root@x.com"), json={"enabled": False})
    data = client.get(EFFECTIVE, headers=auth("user_a@x.com")).get_json()["data"]
    assert data["enabled"] is False


def test_tenant_settings_do_not_leak_to_other_tenants(client, auth, seed):
    from app.constants import Role
    from app.extensions import db
    from app.models.user import User
    from app.utils.uuid_utils import new_uuid

    user_b = User(id=new_uuid(), tenant_id=seed["tenant_b"], name="User B",
                  email="user_b@x.com", role=Role.CHAT_USER, is_active=True)
    user_b.set_password("password123")
    db.session.add(user_b)
    db.session.commit()

    client.put(TENANT, headers=auth("admin_a@x.com"), json={"rate": 2.0})
    # Tenant B's user still gets builtins (no platform row configured).
    data = client.get(EFFECTIVE, headers=auth("user_b@x.com")).get_json()["data"]
    assert data["rate"] == 1.0
    assert data["source"] == "builtin"
