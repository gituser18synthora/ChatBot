from __future__ import annotations

from app.extensions import db
from app.models.tenant import Tenant
from app.models.user import User


def test_delete_tenant_is_soft(client, auth, seed):
    h = auth("root@x.com")
    resp = client.delete(f"/api/v1/admin/tenants/{seed['tenant_a']}", headers=h)
    assert resp.status_code == 200

    # Row is retained (soft-deleted), not erased.
    t = db.session.get(Tenant, seed["tenant_a"])
    assert t is not None
    assert t.deleted_at is not None
    assert t.status == "inactive"

    # Excluded from the active list, and its detail 404s.
    listed = client.get("/api/v1/admin/tenants", headers=h).get_json()
    assert all(x["id"] != seed["tenant_a"] for x in listed["data"])
    assert client.get(f"/api/v1/admin/tenants/{seed['tenant_a']}", headers=h).status_code == 404


def test_deleting_tenant_blocks_its_users_login(client, auth, seed):
    client.delete(f"/api/v1/admin/tenants/{seed['tenant_a']}", headers=auth("root@x.com"))
    # A user of the deleted tenant can no longer authenticate.
    resp = client.post("/api/v1/auth/login", json={"email": "user_a@x.com", "password": "password123"})
    assert resp.status_code == 403


def test_delete_user_is_soft(client, auth, seed):
    h = auth("root@x.com")
    resp = client.delete(f"/api/v1/users/{seed['user_a']}", headers=h)
    assert resp.status_code == 200
    u = db.session.get(User, seed["user_a"])
    assert u is not None and u.deleted_at is not None and u.is_active is False
    # Gone from the list.
    listed = client.get("/api/v1/users", headers=h).get_json()
    assert all(x["id"] != seed["user_a"] for x in listed["data"])
    # And can no longer log in.
    assert client.post("/api/v1/auth/login",
                       json={"email": "user_a@x.com", "password": "password123"}).status_code == 403


def test_tenant_admin_can_delete_chat_user_not_tenant_admin(client, auth, seed):
    h = auth("admin_a@x.com")
    # Create a second tenant admin in tenant A (via super user) to attempt delete.
    root = auth("root@x.com")
    ta = client.post("/api/v1/users", headers=root, json={
        "name": "TA2", "email": "ta2@x.com", "password": "password123",
        "role": "tenant_admin", "tenant_id": seed["tenant_a"]}).get_json()["data"]

    # Tenant admin may delete a chat user in their tenant.
    assert client.delete(f"/api/v1/users/{seed['user_a']}", headers=h).status_code == 200
    # But NOT another tenant admin.
    assert client.delete(f"/api/v1/users/{ta['id']}", headers=h).status_code == 403


def test_cannot_delete_self(client, auth, seed):
    me = client.get("/api/v1/auth/me", headers=auth("root@x.com")).get_json()["data"]["user"]
    assert client.delete(f"/api/v1/users/{me['id']}", headers=auth("root@x.com")).status_code == 400
