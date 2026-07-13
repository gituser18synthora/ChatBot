from __future__ import annotations

from datetime import datetime

from app.constants import DocumentStatus
from app.extensions import db
from app.integrations.openai_client import ChatCompletion
from app.models.document import Document
from app.utils.uuid_utils import new_uuid


def _mock_openai(monkeypatch):
    monkeypatch.setattr(
        "app.integrations.openai_client.chat",
        lambda **k: ChatCompletion(text="Hi", model="gpt-4o-mini", prompt_tokens=5, completion_tokens=3, total_tokens=8),
    )


def _index_doc(seed):
    doc = Document(
        id=new_uuid(), tenant_id=seed["tenant_a"], kb_id=seed["kb_a"],
        original_filename="conversation.pdf", content_type="application/pdf",
        file_size_bytes=10, upload_status=DocumentStatus.COMPLETED,
        uploaded_at=datetime.utcnow(),
    )
    db.session.add(doc)
    db.session.commit()


def test_admin_lists_tenant_conversations(client, auth, seed, monkeypatch, assign_user_kb):
    _mock_openai(monkeypatch)
    # A chat user in tenant A starts a conversation and sends a message.
    _index_doc(seed)
    assign_user_kb()
    uh = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=uh, json={"title": "Hello", "kb_ids": []})
    sid = s.get_json()["data"]["id"]
    client.post(f"/api/v1/chat/sessions/{sid}/messages", headers=uh, json={"message": "Hi there"})

    # Tenant admin can see it in the admin conversations list.
    resp = client.get("/api/v1/admin/conversations", headers=auth("admin_a@x.com"))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["meta"]["total"] == 1
    row = body["data"][0]
    assert row["user_name"] == "User A"
    assert row["message_count"] == 2  # user + assistant


def test_admin_cannot_see_other_tenant_conversations(client, auth, seed, monkeypatch, assign_user_kb):
    _mock_openai(monkeypatch)
    _index_doc(seed)
    assign_user_kb()
    uh = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=uh, json={"kb_ids": []})
    sid = s.get_json()["data"]["id"]
    client.post(f"/api/v1/chat/sessions/{sid}/messages", headers=uh, json={"message": "Hi"})

    # There is no tenant-B admin in the seed; a super admin scoped to tenant B sees none.
    resp = client.get(
        f"/api/v1/admin/conversations?tenant_id={seed['tenant_b']}", headers=auth("root@x.com")
    )
    assert resp.status_code == 200
    assert resp.get_json()["meta"]["total"] == 0


def test_super_admin_can_view_any_tenant_conversation(client, auth, seed, monkeypatch, assign_user_kb):
    # A super admin has no tenant of their own; they must still be able to open
    # (View) any tenant's conversation, matching the platform-wide list.
    _mock_openai(monkeypatch)
    _index_doc(seed)
    assign_user_kb()
    uh = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=uh, json={"title": "Hello", "kb_ids": []})
    sid = s.get_json()["data"]["id"]
    client.post(f"/api/v1/chat/sessions/{sid}/messages", headers=uh, json={"message": "Hi there"})

    resp = client.get(f"/api/v1/admin/conversations/{sid}", headers=auth("root@x.com"))
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["id"] == sid
    assert len(body["messages"]) == 2  # user + assistant


def test_tenant_admin_can_view_own_tenant_conversation(client, auth, seed, monkeypatch, assign_user_kb):
    _mock_openai(monkeypatch)
    _index_doc(seed)
    assign_user_kb()
    uh = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=uh, json={"kb_ids": []})
    sid = s.get_json()["data"]["id"]
    client.post(f"/api/v1/chat/sessions/{sid}/messages", headers=uh, json={"message": "Hi"})

    resp = client.get(f"/api/v1/admin/conversations/{sid}", headers=auth("admin_a@x.com"))
    assert resp.status_code == 200
    assert resp.get_json()["data"]["id"] == sid


def test_chat_user_cannot_access_admin_conversations(client, auth, seed):
    assert client.get("/api/v1/admin/conversations", headers=auth("user_a@x.com")).status_code == 403
