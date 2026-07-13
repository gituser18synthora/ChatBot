from __future__ import annotations


def test_create_kb(client, auth, seed):
    resp = client.post(
        f"/api/v1/tenants/{seed['tenant_a']}/knowledge-bases",
        headers=auth("admin_a@x.com"), json={"kb_name": "Policies"},
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["kb_name"] == "Policies"
    assert data["status"] == "pending"
    assert data["ready"] is False


def test_duplicate_kb_id_same_tenant_updates_existing_row(client, auth, seed):
    kb_id = seed["kb_a"]
    resp = client.post(
        f"/api/v1/tenants/{seed['tenant_a']}/knowledge-bases",
        headers=auth("admin_a@x.com"), json={"id": kb_id, "kb_name": "Updated KB"},
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["id"] == kb_id
    assert data["kb_name"] == "Updated KB"


def test_duplicate_kb_id_other_tenant_is_clean_error(client, auth, seed):
    resp = client.post(
        f"/api/v1/tenants/{seed['tenant_b']}/knowledge-bases",
        headers=auth("root@x.com"), json={"id": seed["kb_a"], "kb_name": "Dupe"},
    )
    assert resp.status_code == 409
    assert "already exists" in resp.get_json()["error"]["message"]


def test_multiple_kbs_per_tenant(client, auth, seed):
    h = auth("admin_a@x.com")
    for name in ("Hero", "HR Policies", "Training"):
        assert client.post(
            f"/api/v1/tenants/{seed['tenant_a']}/knowledge-bases", headers=h, json={"kb_name": name}
        ).status_code == 201
    resp = client.get(f"/api/v1/tenants/{seed['tenant_a']}/knowledge-bases", headers=h)
    assert resp.get_json()["meta"]["total"] == 4  # 1 seeded + 3


def test_cannot_create_kb_in_other_tenant(client, auth, seed):
    resp = client.post(
        f"/api/v1/tenants/{seed['tenant_b']}/knowledge-bases",
        headers=auth("admin_a@x.com"), json={"kb_name": "X"},
    )
    assert resp.status_code == 404
