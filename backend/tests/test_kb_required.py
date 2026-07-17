"""A Knowledge Base is mandatory to use the chatbot.

Enforced in two places:
  - Chat session creation is blocked for a tenant with no KB (chat access).
  - Chat User creation is blocked for a tenant with no KB.
The seeded tenants both own a KB, so these tests spin up a fresh KB-less tenant.
"""
from __future__ import annotations


def _new_tenant_with_admin(client, root, name, admin_email):
    resp = client.post(
        "/api/v1/admin/tenants",
        headers=root,
        json={
            "tenant_name": name,
            "admin_email": admin_email,
            "admin_password": "password123",
            "admin_name": "Admin",
        },
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["data"]


def _add_kb(client, root, tenant_id, name="KB New"):
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/knowledge-bases",
        headers=root,
        json={"kb_name": name},
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["data"]


# ── Chat User creation ────────────────────────────────────────
def test_chat_user_creation_blocked_without_kb(client, auth):
    root = auth("root@x.com")
    t = _new_tenant_with_admin(client, root, "NoKB Corp", "nokb_admin@x.com")

    resp = client.post(
        "/api/v1/users",
        headers=root,
        json={
            "name": "Chat", "email": "chat_nokb@x.com", "password": "password123",
            "role": "chat_user", "tenant_id": t["id"],
        },
    )
    assert resp.status_code == 409, resp.get_json()
    assert resp.get_json()["error"]["code"] == "no_knowledge_base"


def test_chat_user_creation_allowed_after_kb_added(client, auth):
    root = auth("root@x.com")
    t = _new_tenant_with_admin(client, root, "SoonKB Corp", "soonkb_admin@x.com")
    _add_kb(client, root, t["id"])

    resp = client.post(
        "/api/v1/users",
        headers=root,
        json={
            "name": "Chat", "email": "chat_withkb@x.com", "password": "password123",
            "role": "chat_user", "tenant_id": t["id"],
        },
    )
    assert resp.status_code == 201, resp.get_json()


def test_tenant_admin_creation_not_gated_on_kb(client, auth):
    """Only Chat Users require a KB; other roles manage the tenant regardless."""
    root = auth("root@x.com")
    t = _new_tenant_with_admin(client, root, "AdminsOnly Corp", "admins_admin@x.com")

    resp = client.post(
        "/api/v1/users",
        headers=root,
        json={
            "name": "Second Admin", "email": "second_admin@x.com", "password": "password123",
            "role": "tenant_admin", "tenant_id": t["id"],
        },
    )
    assert resp.status_code == 201, resp.get_json()


# ── Chat access ───────────────────────────────────────────────
def test_availability_reflects_kb_presence(client, auth):
    root = auth("root@x.com")
    _new_tenant_with_admin(client, root, "NoKB Chat Corp", "nokb_chat@x.com")

    # Seeded Tenant A owns a KB; the fresh tenant does not.
    with_kb = client.get("/api/v1/chat/availability", headers=auth("admin_a@x.com"))
    assert with_kb.status_code == 200
    assert with_kb.get_json()["data"]["has_knowledge_base"] is True

    without = client.get("/api/v1/chat/availability", headers=auth("nokb_chat@x.com"))
    assert without.status_code == 200
    assert without.get_json()["data"]["has_knowledge_base"] is False


def test_chat_session_blocked_without_kb(client, auth):
    root = auth("root@x.com")
    _new_tenant_with_admin(client, root, "NoKB Session Corp", "nokb_session@x.com")
    h = auth("nokb_session@x.com")

    resp = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    assert resp.status_code == 409, resp.get_json()
    assert resp.get_json()["error"]["code"] == "no_knowledge_base"


def test_chat_session_allowed_after_kb_added(client, auth):
    root = auth("root@x.com")
    t = _new_tenant_with_admin(client, root, "SoonKB Session Corp", "soonkb_session@x.com")
    h = auth("soonkb_session@x.com")

    blocked = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    assert blocked.status_code == 409

    _add_kb(client, root, t["id"])
    ok = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    assert ok.status_code == 201, ok.get_json()
