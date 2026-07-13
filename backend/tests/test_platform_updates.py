"""Tests for the 2026-07-09 platform updates:

- tenant creation can no longer set is_super_tenant (designation is update-only)
- per-tenant RAG answering mode (rag_only / rag_first)
- automatic chat-title generation from the first user message
- initial KB scoping at user-creation time (kb_ids)
- /chat/knowledge-bases exposes ingestion visibility (document_count/ready)
"""
from __future__ import annotations

from datetime import datetime

from app.constants import DocumentStatus, KBStatus, RagMode
from app.extensions import db
from app.integrations.kmrag_client import KmragQueryResult
from app.integrations.openai_client import ChatCompletion, OpenAIUnavailable
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.tenant import Tenant
from app.utils.uuid_utils import new_uuid


def _mock_openai(monkeypatch, text="Mocked answer."):
    monkeypatch.setattr(
        "app.integrations.openai_client.chat",
        lambda **k: ChatCompletion(text=text, model="gpt-4o-mini",
                                   prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def _index_doc(seed, kb_key="kb_a"):
    doc = Document(
        id=new_uuid(), tenant_id=seed["tenant_a"], kb_id=seed[kb_key],
        original_filename="hero.pdf", content_type="application/pdf", file_size_bytes=10,
        upload_status=DocumentStatus.COMPLETED, uploaded_at=datetime.utcnow(),
    )
    db.session.add(doc)
    db.session.commit()


def _set_rag_mode(tenant_id, mode):
    tenant = db.session.get(Tenant, tenant_id)
    tenant.rag_mode = mode
    db.session.commit()


# ── Super Tenant designation is update-only ───────────────────
def test_tenant_create_rejects_is_super_tenant(client, auth, seed):
    resp = client.post("/api/v1/admin/tenants", headers=auth("root@x.com"), json={
        "tenant_name": "Sneaky", "is_super_tenant": True,
        "admin_email": "sneaky@x.com", "admin_password": "password123",
    })
    assert resp.status_code == 422

    ok = client.post("/api/v1/admin/tenants", headers=auth("root@x.com"), json={
        "tenant_name": "Normal Co",
        "admin_email": "normal@x.com", "admin_password": "password123",
    })
    assert ok.status_code == 201
    assert ok.get_json()["data"]["is_super_tenant"] is False
    assert ok.get_json()["data"]["rag_mode"] == RagMode.RAG_FIRST


# ── Per-tenant RAG mode ───────────────────────────────────────
def test_rag_only_forces_kb_answers_for_general_questions(client, auth, seed, monkeypatch, assign_user_kb):
    """In rag_only mode even a clearly general question goes through retrieval."""
    _set_rag_mode(seed["tenant_a"], RagMode.RAG_ONLY)
    _index_doc(seed)

    def fail_openai(**kwargs):
        raise AssertionError("General AI must not be called in rag_only mode")

    monkeypatch.setattr("app.services.chat_service._answer_via_general", fail_openai)
    monkeypatch.setattr(
        "app.services.retrieval_service.query_kmrag",
        lambda **k: KmragQueryResult(
            answer="KB answer.", context_found=True,
            sources=[{"document_name": "hero.pdf", "page_number": 1, "score": 0.9}],
            metadata={}, request_id=k["request_id"],
        ),
    )
    # Title generation still uses OpenAI — let it succeed quietly.
    _mock_openai(monkeypatch, text="Some Title")

    assign_user_kb()
    h = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    session_id = s.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       headers=h, json={"message": "What is Python?"})
    assert resp.status_code == 200
    msg = resp.get_json()["data"]["assistant_message"]
    assert msg["answer_mode"] == "document_rag"
    assert msg["message_text"] == "KB answer."


def test_rag_only_without_any_ready_kb_gets_clean_message(client, auth, seed, monkeypatch):
    _set_rag_mode(seed["tenant_a"], RagMode.RAG_ONLY)
    # Deactivate the tenant's only KB so the user's effective set is empty.
    kb = db.session.get(KnowledgeBase, seed["kb_a"])
    kb.status = KBStatus.INACTIVE
    db.session.commit()

    monkeypatch.setattr("app.services.chat_service._answer_via_general",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no general AI")))
    _mock_openai(monkeypatch, text="Some Title")

    h = auth("user_a@x.com")
    # Session creation never blocks; the message itself explains the KB state.
    s = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    assert s.status_code == 201
    session_id = s.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       headers=h, json={"message": "What is the incentive?"})
    msg = resp.get_json()["data"]["assistant_message"]
    assert msg["answer_mode"] == "no_document_evidence"
    assert "no knowledge base is available" in msg["message_text"].lower()


def test_tenant_admin_can_set_rag_mode_via_profile(client, auth, seed):
    resp = client.put("/api/v1/profile/tenant", headers=auth("admin_a@x.com"),
                      json={"rag_mode": "rag_only"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["rag_mode"] == "rag_only"

    bad = client.put("/api/v1/profile/tenant", headers=auth("admin_a@x.com"),
                     json={"rag_mode": "everything_goes"})
    assert bad.status_code == 422

    # Chat users cannot touch tenant settings.
    denied = client.put("/api/v1/profile/tenant", headers=auth("user_a@x.com"),
                        json={"rag_mode": "rag_first"})
    assert denied.status_code == 403


def test_super_admin_can_set_rag_mode_via_tenant_update(client, auth, seed):
    resp = client.put(f"/api/v1/admin/tenants/{seed['tenant_a']}",
                      headers=auth("root@x.com"), json={"rag_mode": "rag_only"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["rag_mode"] == "rag_only"


# ── Automatic chat titles ─────────────────────────────────────
def test_first_message_generates_title(client, auth, seed, monkeypatch):
    _mock_openai(monkeypatch, text="Refund Policy Question")
    h = auth("admin_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    session_id = s.get_json()["data"]["id"]
    assert s.get_json()["data"]["title"] == "New Chat"

    resp = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       headers=h, json={"message": "What is the refund policy?"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["session_title"] == "Refund Policy Question"

    detail = client.get(f"/api/v1/chat/sessions/{session_id}", headers=h)
    assert detail.get_json()["data"]["title"] == "Refund Policy Question"


def test_title_generation_failure_falls_back_to_message_snippet(client, auth, seed, monkeypatch, assign_user_kb):
    def broken_openai(**kwargs):
        raise OpenAIUnavailable("down")

    monkeypatch.setattr("app.integrations.openai_client.chat", broken_openai)
    # Ground the message in a KB so the answer path doesn't need OpenAI either.
    _index_doc(seed)
    monkeypatch.setattr(
        "app.services.retrieval_service.query_kmrag",
        lambda **k: KmragQueryResult(
            answer="From the docs.", context_found=True,
            sources=[{"document_name": "hero.pdf", "page_number": 1, "score": 0.9}],
            metadata={}, request_id=k["request_id"],
        ),
    )
    assign_user_kb()
    h = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    session_id = s.get_json()["data"]["id"]
    resp = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages", headers=h,
        json={"message": "According to the document what is the dealer incentive percentage"})
    assert resp.status_code == 200
    title = resp.get_json()["data"]["session_title"]
    assert title == "According to the document what is"  # first 6 words


def test_manual_title_is_never_overwritten(client, auth, seed, monkeypatch):
    _mock_openai(monkeypatch, text="Should Not Appear")
    h = auth("admin_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"title": "My chosen title", "kb_ids": []})
    session_id = s.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       headers=h, json={"message": "What is Python?"})
    assert resp.get_json()["data"]["session_title"] == "My chosen title"


def test_second_message_does_not_retitle(client, auth, seed, monkeypatch):
    _mock_openai(monkeypatch, text="First Title")
    h = auth("admin_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    session_id = s.get_json()["data"]["id"]
    client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                headers=h, json={"message": "What is Python?"})

    _mock_openai(monkeypatch, text="Second Title")
    resp = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       headers=h, json={"message": "And what is Redis?"})
    assert resp.get_json()["data"]["session_title"] == "First Title"


# ── KB scoping at user creation ───────────────────────────────
def test_create_user_with_initial_kb_scope(client, auth, seed):
    h = auth("admin_a@x.com")
    resp = client.post("/api/v1/users", headers=h, json={
        "name": "Scoped User", "email": "scoped@x.com", "password": "password123",
        "role": "chat_user", "kb_ids": [seed["kb_a"]],
    })
    assert resp.status_code == 201, resp.get_json()
    user_id = resp.get_json()["data"]["id"]

    access = client.get(f"/api/v1/users/{user_id}/knowledge-bases", headers=h).get_json()["data"]
    assert access["assigned_kb_ids"] == [seed["kb_a"]]
    assert access["uses_all_kbs"] is False


def test_create_user_with_foreign_kb_is_rejected_atomically(client, auth, seed):
    h = auth("admin_a@x.com")
    resp = client.post("/api/v1/users", headers=h, json={
        "name": "Bad Scope", "email": "badscope@x.com", "password": "password123",
        "role": "chat_user", "kb_ids": [seed["kb_b"]],  # belongs to tenant B
    })
    assert resp.status_code == 403
    # The user must not exist at all (validation happens before creation).
    from app.models.user import User
    assert User.query.filter_by(email="badscope@x.com").first() is None


def test_create_chat_user_without_kb_ids_uses_all_tenant_kbs(client, auth, seed):
    h = auth("admin_a@x.com")
    resp = client.post("/api/v1/users", headers=h, json={
        "name": "Open User", "email": "open@x.com", "password": "password123",
        "role": "chat_user",
    })
    assert resp.status_code == 201
    user_id = resp.get_json()["data"]["id"]
    access = client.get(f"/api/v1/users/{user_id}/knowledge-bases", headers=h).get_json()["data"]
    assert access["assigned_kb_ids"] == []
    assert access["uses_all_kbs"] is True


def test_kb_ids_rejected_when_creating_tenant_admin(client, auth, seed):
    resp = client.post("/api/v1/users", headers=auth("root@x.com"), json={
        "name": "Scoped Admin", "email": "scoped-admin@x.com", "password": "password123",
        "role": "tenant_admin", "tenant_id": seed["tenant_a"], "kb_ids": [seed["kb_a"]],
    })
    assert resp.status_code == 422
    assert "only available for Chat Users" in resp.get_json()["error"]["message"]


# ── Chat KB endpoint ingestion visibility ─────────────────────
def test_chat_kb_endpoint_reports_document_counts(client, auth, seed, assign_user_kb):
    _index_doc(seed)
    assign_user_kb()
    h = auth("user_a@x.com")
    resp = client.get("/api/v1/chat/knowledge-bases", headers=h)
    assert resp.status_code == 200
    items = resp.get_json()["data"]
    kb = next(i for i in items if i["id"] == seed["kb_a"])
    assert kb["document_count"] == 1
    assert kb["indexed_count"] == 1
    assert kb["ready"] is True


def test_chat_kb_endpoint_flags_unindexed_kb(client, auth, seed, assign_user_kb):
    assign_user_kb()
    h = auth("user_a@x.com")
    resp = client.get("/api/v1/chat/knowledge-bases", headers=h)
    kb = next(i for i in resp.get_json()["data"] if i["id"] == seed["kb_a"])
    assert kb["document_count"] == 0
    assert kb["ready"] is False
