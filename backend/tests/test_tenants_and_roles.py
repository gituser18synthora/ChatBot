from __future__ import annotations


def test_tenant_code_auto_generated_from_name(client, auth, seed):
    resp = client.post(
        "/api/v1/admin/tenants",
        headers=auth("root@x.com"),
        json={"tenant_name": "Acme Widgets Inc"},  # no tenant_code supplied
    )
    assert resp.status_code == 201
    assert resp.get_json()["data"]["tenant_code"] == "acme-widgets-inc"


def test_duplicate_tenant_name_gets_distinct_codes(client, auth, seed):
    h = auth("root@x.com")
    first = client.post("/api/v1/admin/tenants", headers=h, json={"tenant_name": "Globex"})
    second = client.post("/api/v1/admin/tenants", headers=h, json={"tenant_name": "Globex"})
    assert first.get_json()["data"]["tenant_code"] == "globex"
    assert second.get_json()["data"]["tenant_code"] == "globex-2"


def test_super_admin_persisted_in_db(client, auth, seed):
    # Super Admin creates another Super Admin (no tenant) via the users API.
    resp = client.post(
        "/api/v1/users",
        headers=auth("root@x.com"),
        json={"name": "Second Root", "email": "root2@x.com", "password": "password123", "role": "super_admin"},
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["role"] == "super_admin"
    assert data["tenant_id"] is None

    # It is a real DB row and can authenticate.
    from app.models.user import User
    row = User.query.filter_by(email="root2@x.com").first()
    assert row is not None and row.role == "super_admin" and row.tenant_id is None
    login = client.post("/api/v1/auth/login", json={"email": "root2@x.com", "password": "password123"})
    assert login.status_code == 200


def test_tenant_admin_cannot_create_super_admin(client, auth, seed):
    resp = client.post(
        "/api/v1/users",
        headers=auth("admin_a@x.com"),
        json={"name": "Sneaky", "email": "sneaky@x.com", "password": "password123", "role": "super_admin"},
    )
    assert resp.status_code == 403


def test_tenant_admin_cannot_create_tenant_admin(client, auth, seed):
    resp = client.post(
        "/api/v1/users",
        headers=auth("admin_a@x.com"),
        json={"name": "Deputy", "email": "deputy@x.com", "password": "password123", "role": "tenant_admin"},
    )
    assert resp.status_code == 403
    assert "Chat Users" in resp.get_json()["error"]["message"]


def test_tenant_admin_can_create_chat_user(client, auth, seed):
    resp = client.post(
        "/api/v1/users",
        headers=auth("admin_a@x.com"),
        json={"name": "Aiden", "email": "aiden@x.com", "password": "password123", "role": "chat_user"},
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["role"] == "chat_user"
    assert data["tenant_id"] == seed["tenant_a"]  # forced to the admin's own tenant


def test_super_user_can_still_create_tenant_admin(client, auth, seed):
    resp = client.post(
        "/api/v1/users",
        headers=auth("root@x.com"),
        json={"name": "TA", "email": "ta@x.com", "password": "password123",
              "role": "tenant_admin", "tenant_id": seed["tenant_a"]},
    )
    assert resp.status_code == 201
    assert resp.get_json()["data"]["role"] == "tenant_admin"
