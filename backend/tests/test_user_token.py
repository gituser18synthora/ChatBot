"""Chat User access-token generation (Tenant Admin)."""
from __future__ import annotations

from app.models.user_token import UserToken


def test_tenant_admin_generates_token_for_chat_user(client, auth, seed, assign_user_kb):
    assign_user_kb(seed["user_a"], seed["kb_a"])
    resp = client.post(f"/api/v1/users/{seed['user_a']}/token", headers=auth("admin_a@x.com"))
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["user_id"] == seed["user_a"]
    assert data["tenant_id"] == seed["tenant_a"]
    assert data["kb_ids"] == [seed["kb_a"]]
    assert data["token"]
    assert len(data["token"]) == 32
    assert data["token"].isalnum()

    row = UserToken.query.filter_by(user_id=seed["user_a"]).one()
    assert row.token == data["token"]
    assert row.kb_ids == [seed["kb_a"]]


def test_regenerate_replaces_previous_token(client, auth, seed):
    first = client.post(f"/api/v1/users/{seed['user_a']}/token", headers=auth("admin_a@x.com"))
    assert first.status_code == 201
    old = first.get_json()["data"]["token"]

    second = client.post(f"/api/v1/users/{seed['user_a']}/token", headers=auth("admin_a@x.com"))
    assert second.status_code == 201
    new = second.get_json()["data"]["token"]
    assert new != old
    assert UserToken.query.filter_by(user_id=seed["user_a"]).count() == 1


def test_get_token_returns_stored_row(client, auth, seed):
    created = client.post(f"/api/v1/users/{seed['user_a']}/token", headers=auth("admin_a@x.com"))
    token = created.get_json()["data"]["token"]

    resp = client.get(f"/api/v1/users/{seed['user_a']}/token", headers=auth("admin_a@x.com"))
    assert resp.status_code == 200
    assert resp.get_json()["data"]["token"] == token


def test_cannot_generate_token_for_tenant_admin(client, auth, seed):
    resp = client.post(f"/api/v1/users/{seed['admin_a']}/token", headers=auth("admin_a@x.com"))
    assert resp.status_code == 400
    assert "Chat Users" in resp.get_json()["error"]["message"]


def test_tenant_admin_cannot_token_other_tenant_user(client, auth, seed):
    other = client.post(
        "/api/v1/users",
        headers=auth("root@x.com"),
        json={
            "name": "User B",
            "email": "user_b@x.com",
            "password": "password123",
            "role": "chat_user",
            "tenant_id": seed["tenant_b"],
        },
    ).get_json()["data"]
    resp = client.post(f"/api/v1/users/{other['id']}/token", headers=auth("admin_a@x.com"))
    assert resp.status_code == 404


def test_chat_user_cannot_generate_token(client, auth, seed):
    resp = client.post(f"/api/v1/users/{seed['user_a']}/token", headers=auth("user_a@x.com"))
    assert resp.status_code == 403


def test_list_users_includes_stored_token(client, auth, seed):
    created = client.post(f"/api/v1/users/{seed['user_a']}/token", headers=auth("admin_a@x.com"))
    assert created.status_code == 201
    token = created.get_json()["data"]["token"]

    resp = client.get("/api/v1/users?page=1", headers=auth("admin_a@x.com"))
    assert resp.status_code == 200
    users = resp.get_json()["data"]
    chat_user = next(u for u in users if u["id"] == seed["user_a"])
    assert chat_user["token"] == token
    admin = next(u for u in users if u["id"] == seed["admin_a"])
    assert admin["token"] is None
