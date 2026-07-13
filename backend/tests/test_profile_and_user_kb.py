from __future__ import annotations


# ── Tenant creation now provisions a login ────────────────────
def test_create_tenant_creates_working_login(client, auth):
    resp = client.post(
        "/api/v1/admin/tenants",
        headers=auth("root@x.com"),
        json={
            "tenant_name": "Northwind",
            "admin_name": "Nancy",
            "admin_email": "nancy@northwind.test",
            "admin_password": "password123",
        },
    )
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()["data"]
    assert body["admin"]["email"] == "nancy@northwind.test"

    # The new tenant admin can authenticate immediately.
    login = client.post("/api/v1/auth/login",
                        json={"email": "nancy@northwind.test", "password": "password123"})
    assert login.status_code == 200
    me = login.get_json()["data"]["user"]
    assert me["role"] == "tenant_admin"
    assert me["tenant_id"] == body["id"]


def test_create_tenant_duplicate_admin_email_conflicts(client, auth):
    resp = client.post(
        "/api/v1/admin/tenants",
        headers=auth("root@x.com"),
        json={"tenant_name": "Dup Co", "admin_email": "root@x.com", "admin_password": "password123"},
    )
    assert resp.status_code == 409
    # The tenant must NOT be created when its login can't be attached.
    from app.models.tenant import Tenant
    assert Tenant.query.filter_by(tenant_name="Dup Co").first() is None


# ── Profile: self-service ─────────────────────────────────────
def test_profile_returns_user_and_tenant(client, auth, seed):
    resp = client.get("/api/v1/profile", headers=auth("admin_a@x.com"))
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["user"]["email"] == "admin_a@x.com"
    assert data["tenant"]["id"] == seed["tenant_a"]


def test_tenant_admin_updates_own_tenant(client, auth, seed):
    resp = client.put("/api/v1/profile/tenant", headers=auth("admin_a@x.com"),
                      json={"tenant_name": "Tenant A Renamed", "contact_name": "Ops"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["tenant_name"] == "Tenant A Renamed"


def test_super_admin_cannot_use_tenant_profile(client, auth, seed):
    # Super Admin has no tenant; the tenant-profile route is Tenant-Admin only.
    resp = client.put("/api/v1/profile/tenant", headers=auth("root@x.com"),
                      json={"tenant_name": "X"})
    assert resp.status_code == 403


def test_chat_user_can_change_own_password(client, auth, seed):
    resp = client.put("/api/v1/profile/password", headers=auth("user_a@x.com"),
                      json={"current_password": "password123", "new_password": "newpassword456"})
    assert resp.status_code == 200
    assert client.post("/api/v1/auth/login",
                       json={"email": "user_a@x.com", "password": "password123"}).status_code == 401
    assert client.post("/api/v1/auth/login",
                       json={"email": "user_a@x.com", "password": "newpassword456"}).status_code == 200


def test_change_password_wrong_current_rejected(client, auth, seed):
    resp = client.put("/api/v1/profile/password", headers=auth("user_a@x.com"),
                      json={"current_password": "wrong", "new_password": "newpassword456"})
    assert resp.status_code == 400


# ── Per-user KB assignment ────────────────────────────────────
def _create_kb(client, auth, tenant_id, name):
    resp = client.post(f"/api/v1/tenants/{tenant_id}/knowledge-bases",
                       headers=auth("root@x.com"), json={"kb_name": name})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["data"]["id"]


def _index_completed_doc(seed, kb_id, name="doc.pdf"):
    """Give a KB an indexed document so reconciliation keeps it chat-ready."""
    from datetime import datetime

    from app.constants import DocumentStatus, KBStatus
    from app.extensions import db
    from app.models.document import Document
    from app.models.knowledge_base import KnowledgeBase
    from app.utils.uuid_utils import new_uuid

    db.session.add(Document(
        id=new_uuid(), tenant_id=seed["tenant_a"], kb_id=kb_id,
        original_filename=name, content_type="application/pdf", file_size_bytes=10,
        upload_status=DocumentStatus.COMPLETED, uploaded_at=datetime.utcnow(),
        processed_at=datetime.utcnow(),
    ))
    db.session.get(KnowledgeBase, kb_id).status = KBStatus.READY
    db.session.commit()


def test_user_kb_assignment_scopes_selectable_set(client, auth, seed):
    kb2 = _create_kb(client, auth, seed["tenant_a"], "KB A2")
    _index_completed_doc(seed, seed["kb_a"], "one.pdf")
    _index_completed_doc(seed, kb2, "two.pdf")

    # A Chat User with no assignment automatically searches ALL tenant KBs.
    access = client.get(
        f"/api/v1/users/{seed['user_a']}/knowledge-bases",
        headers=auth("admin_a@x.com"),
    ).get_json()["data"]
    assert access["assigned_kb_ids"] == []
    assert access["uses_all_kbs"] is True

    sel = client.get("/api/v1/chat/knowledge-bases", headers=auth("user_a@x.com")).get_json()["data"]
    assert {k["id"] for k in sel} == {seed["kb_a"], kb2}

    # Assign only kb_a to the user: now they are restricted to kb_a.
    put = client.put(f"/api/v1/users/{seed['user_a']}/knowledge-bases",
                     headers=auth("admin_a@x.com"), json={"kb_ids": [seed["kb_a"]]})
    assert put.status_code == 200
    assert put.get_json()["data"]["assigned_kb_ids"] == [seed["kb_a"]]

    sel2 = client.get("/api/v1/chat/knowledge-bases", headers=auth("user_a@x.com")).get_json()["data"]
    assert {k["id"] for k in sel2} == {seed["kb_a"]}


def test_tenant_admin_without_assignment_uses_all_ready_tenant_kbs_for_chat(client, auth, seed):
    kb2 = _create_kb(client, auth, seed["tenant_a"], "KB A2")

    access = client.get(
        f"/api/v1/users/{seed['admin_a']}/knowledge-bases",
        headers=auth("root@x.com"),
    ).get_json()["data"]
    assert access["assigned_kb_ids"] == []
    assert access["uses_all_kbs"] is True
    assert {k["id"] for k in access["available"]} == {seed["kb_a"], kb2}

    # The chat picker only returns KBs that are actually ready in KMRAG.
    # These have no indexed documents, so nothing is chat-ready yet.
    sel = client.get("/api/v1/chat/knowledge-bases", headers=auth("admin_a@x.com")).get_json()["data"]
    assert sel == []


def test_tenant_admin_cannot_be_scoped_to_kbs(client, auth, seed):
    # KB assignment is a Chat User concept; admins always use all tenant KBs.
    resp = client.put(f"/api/v1/users/{seed['admin_a']}/knowledge-bases",
                      headers=auth("root@x.com"), json={"kb_ids": [seed["kb_a"]]})
    assert resp.status_code == 422
    assert "only available for Chat Users" in resp.get_json()["error"]["message"]


def test_cannot_assign_cross_tenant_kb(client, auth, seed):
    resp = client.put(f"/api/v1/users/{seed['user_a']}/knowledge-bases",
                      headers=auth("root@x.com"), json={"kb_ids": [seed["kb_b"]]})
    assert resp.status_code == 403


def test_tenant_admin_cannot_scope_other_tenant_user(client, auth, seed):
    # admin_a (tenant A) cannot touch a user in tenant B. Create one first.
    other = client.post("/api/v1/users", headers=auth("root@x.com"),
                        json={"name": "B User", "email": "buser@x.com", "password": "password123",
                              "role": "chat_user", "tenant_id": seed["tenant_b"]}).get_json()["data"]
    resp = client.get(f"/api/v1/users/{other['id']}/knowledge-bases", headers=auth("admin_a@x.com"))
    assert resp.status_code == 404


def test_clearing_chat_user_assignment_restores_all_tenant_kbs(client, auth, seed):
    kb2 = _create_kb(client, auth, seed["tenant_a"], "KB A3")
    _index_completed_doc(seed, seed["kb_a"], "one.pdf")
    _index_completed_doc(seed, kb2, "three.pdf")
    client.put(f"/api/v1/users/{seed['user_a']}/knowledge-bases",
               headers=auth("admin_a@x.com"), json={"kb_ids": [seed["kb_a"]]})
    sel = client.get("/api/v1/chat/knowledge-bases", headers=auth("user_a@x.com")).get_json()["data"]
    assert {k["id"] for k in sel} == {seed["kb_a"]}

    # Clearing the assignment returns the user to the automatic all-KB scope.
    cleared = client.put(f"/api/v1/users/{seed['user_a']}/knowledge-bases",
                         headers=auth("admin_a@x.com"), json={"kb_ids": []})
    data = cleared.get_json()["data"]
    assert data["uses_all_kbs"] is True
    sel2 = client.get("/api/v1/chat/knowledge-bases", headers=auth("user_a@x.com")).get_json()["data"]
    assert {k["id"] for k in sel2} == {seed["kb_a"], kb2}
