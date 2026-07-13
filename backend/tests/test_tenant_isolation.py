from __future__ import annotations


def test_tenant_admin_cannot_list_tenants(client, auth):
    # Tenant listing is super-admin only.
    assert client.get("/api/v1/admin/tenants", headers=auth("admin_a@x.com")).status_code == 403


def test_super_admin_lists_tenants(client, auth, seed):
    resp = client.get("/api/v1/admin/tenants", headers=auth("root@x.com"))
    assert resp.status_code == 200
    assert resp.get_json()["meta"]["total"] == 2


def test_tenant_admin_cannot_read_other_tenant_kbs(client, auth, seed):
    # Admin A tries to read Tenant B's KB list -> 404 (isolation, no existence leak).
    resp = client.get(f"/api/v1/tenants/{seed['tenant_b']}/knowledge-bases", headers=auth("admin_a@x.com"))
    assert resp.status_code == 404


def test_tenant_admin_reads_own_kbs(client, auth, seed):
    resp = client.get(f"/api/v1/tenants/{seed['tenant_a']}/knowledge-bases", headers=auth("admin_a@x.com"))
    assert resp.status_code == 200
    assert resp.get_json()["meta"]["total"] == 1


def test_chat_user_cannot_access_admin(client, auth, seed):
    resp = client.get(f"/api/v1/tenants/{seed['tenant_a']}/knowledge-bases", headers=auth("user_a@x.com"))
    assert resp.status_code == 403
