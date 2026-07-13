from __future__ import annotations

from datetime import datetime

from app.constants import DocumentStatus
from app.extensions import db
from app.integrations.kmrag_client import KmragQueryResult
from app.integrations.openai_client import ChatCompletion
from app.models.document import Document
from app.models.tenant import Tenant
from app.utils.uuid_utils import new_uuid


def _make_super_tenant(seed):
    """Promote tenant_b to Super Tenant and give it a KB with an indexed doc."""
    st = Tenant.query.get(seed["tenant_b"])
    st.is_super_tenant = True
    doc = Document(
        id=new_uuid(), tenant_id=st.id, kb_id=seed["kb_b"],
        original_filename="shared.pdf", content_type="application/pdf", file_size_bytes=10,
        upload_status=DocumentStatus.COMPLETED, uploaded_at=datetime.utcnow(),
    )
    db.session.add(doc)
    db.session.commit()
    return st


def test_only_one_super_tenant(client, auth, seed):
    h = auth("root@x.com")
    # Promote tenant A.
    client.put(f"/api/v1/admin/tenants/{seed['tenant_a']}", headers=h, json={"is_super_tenant": True})
    # Promote tenant B — A must be demoted automatically.
    client.put(f"/api/v1/admin/tenants/{seed['tenant_b']}", headers=h, json={"is_super_tenant": True})
    a = client.get(f"/api/v1/admin/tenants/{seed['tenant_a']}", headers=h).get_json()["data"]
    b = client.get(f"/api/v1/admin/tenants/{seed['tenant_b']}", headers=h).get_json()["data"]
    assert b["is_super_tenant"] is True
    assert a["is_super_tenant"] is False


def test_assign_kb_and_selectable_includes_shared(client, auth, seed):
    _make_super_tenant(seed)  # tenant_b is super, owns kb_b
    h = auth("root@x.com")
    # Share the super-tenant KB (kb_b) with tenant A.
    resp = client.post(f"/api/v1/super-tenant/knowledge-bases/{seed['kb_b']}/assignments",
                       headers=h, json={"tenant_id": seed["tenant_a"]})
    assert resp.status_code == 201

    # Tenant admins can select both local and shared KBs for assignment.
    sel = client.get(f"/api/v1/tenants/{seed['tenant_a']}/knowledge-bases/selectable",
                     headers=auth("admin_a@x.com")).get_json()["data"]
    ids = {k["id"]: k for k in sel}
    assert seed["kb_b"] in ids
    assert ids[seed["kb_b"]]["shared"] is True
    assert ids[seed["kb_a"]]["shared"] is False

    denied = client.get(f"/api/v1/tenants/{seed['tenant_a']}/knowledge-bases/selectable",
                        headers=auth("user_a@x.com"))
    assert denied.status_code == 403


def test_shared_kb_query_uses_owner_tenant(client, auth, seed, monkeypatch, assign_user_kb):
    st = _make_super_tenant(seed)
    h = auth("root@x.com")
    client.post(f"/api/v1/super-tenant/knowledge-bases/{seed['kb_b']}/assignments",
               headers=h, json={"tenant_id": seed["tenant_a"]})
    assign_user_kb(kb_id=seed["kb_b"])

    monkeypatch.setattr(
        "app.integrations.openai_client.chat",
        lambda **k: ChatCompletion(text="G", model="gpt-4o-mini", prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )
    captured = {}
    def fake_query(**kwargs):
        captured.update(kwargs)
        return KmragQueryResult(answer="Shared answer.", context_found=True,
                                sources=[{"document_name": "shared.pdf", "page_number": 1, "score": 0.9}],
                                metadata={"steps": {"retrieval": {"documents_retrieved": 1}}},
                                request_id=kwargs["request_id"])
    monkeypatch.setattr("app.services.retrieval_service.query_kmrag", fake_query)

    # Tenant A user chats with the SHARED kb_b.
    uh = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=uh, json={"kb_ids": []})
    assert s.status_code == 201
    sid = s.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/chat/sessions/{sid}/messages", headers=uh,
                       json={"message": "According to the document, what is shared?"})
    assert resp.status_code == 200
    msg = resp.get_json()["data"]["assistant_message"]
    assert msg["answer_mode"] == "document_rag"
    # KMRAG was queried under the KB OWNER (super tenant B), not the requester (A).
    assert captured["tenant_id"] == st.id
    assert captured["kb_ids"] == [seed["kb_b"]]


def test_cannot_assign_non_super_tenant_kb(client, auth, seed):
    _make_super_tenant(seed)  # tenant_b super; kb_a belongs to tenant_a (not shareable)
    resp = client.post(f"/api/v1/super-tenant/knowledge-bases/{seed['kb_a']}/assignments",
                       headers=auth("root@x.com"), json={"tenant_id": seed["tenant_a"]})
    assert resp.status_code == 409


def test_tenant_admin_cannot_access_super_tenant_panel(client, auth, seed):
    assert client.get("/api/v1/super-tenant/knowledge-bases", headers=auth("admin_a@x.com")).status_code == 403
