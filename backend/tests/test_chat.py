from __future__ import annotations

from datetime import datetime

from app.constants import DocumentStatus
from app.extensions import db
from app.integrations.kmrag_client import KmragQueryResult
from app.integrations.openai_client import ChatCompletion
from app.models.document import Document
from app.utils.uuid_utils import new_uuid


def _mock_openai(monkeypatch, text="General answer."):
    monkeypatch.setattr(
        "app.integrations.openai_client.chat",
        lambda **k: ChatCompletion(text=text, model="gpt-4o-mini",
                                   prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def _db_sources(message_id):
    """Persisted source rows for a message — sources are stored for every
    grounded answer regardless of who may see them in API responses."""
    from app.models.chat_source import ChatSource
    return ChatSource.query.filter_by(message_id=message_id).all()


def _index_doc(seed, kb_key="kb_a", name="hero.pdf", status=DocumentStatus.COMPLETED):
    """Give a KB an ingested document so it is 'queryable' in KMRAG's view."""
    doc = Document(
        id=new_uuid(), tenant_id=seed["tenant_a"], kb_id=seed[kb_key],
        original_filename=name, content_type="application/pdf", file_size_bytes=10,
        upload_status=status, uploaded_at=datetime.utcnow(),
    )
    db.session.add(doc)
    db.session.commit()
    return doc


def test_general_chat_route(client, auth, seed, monkeypatch):
    _mock_openai(monkeypatch)
    h = auth("admin_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"title": "Hi", "kb_ids": []})
    session_id = s.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       headers=h, json={"message": "What is Python?"})
    assert resp.status_code == 200
    msg = resp.get_json()["data"]["assistant_message"]
    assert msg["answer_mode"] == "normal"
    assert msg["message_text"] == "General answer."


def test_rag_chat_route_with_sources(client, auth, seed, monkeypatch, assign_user_kb):
    _mock_openai(monkeypatch)  # for the router classification fallback path

    def fake_query(**kwargs):
        return KmragQueryResult(
            answer="The dealer incentive is 5%.",
            context_found=True,
            sources=[{"document_name": "Hero.pdf", "page_number": 3, "score": 0.82}],
            metadata={"steps": {"retrieval": {"documents_retrieved": 1}}},
            request_id=kwargs["request_id"],
        )

    monkeypatch.setattr("app.services.retrieval_service.query_kmrag", fake_query)
    _index_doc(seed)  # KB must have an ingested document to be queryable
    assign_user_kb()
    h = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"title": "Docs", "kb_ids": []})
    session_id = s.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       headers=h, json={"message": "What does the uploaded document say about dealer incentive?"})
    assert resp.status_code == 200
    msg = resp.get_json()["data"]["assistant_message"]
    assert msg["answer_mode"] == "document_rag"
    # Chat Users never see sources (KB internals) — but the rows ARE persisted
    # so admins reviewing the conversation get the citations.
    assert msg["sources"] == []
    rows = _db_sources(msg["id"])
    assert rows[0].document_name == "Hero.pdf"
    assert rows[0].page_number == 3


def test_admin_sees_sources_chat_user_does_not(client, auth, seed, monkeypatch):
    # Source visibility is role-gated: Tenant Admin (and Super Admin) get the
    # sources in API responses; Chat Users get an empty list (tested above).
    _mock_openai(monkeypatch)

    def fake_query(**kwargs):
        return KmragQueryResult(
            answer="The dealer incentive is 5%.",
            context_found=True,
            sources=[{"document_name": "Hero.pdf", "page_number": 3, "score": 0.82}],
            metadata={"steps": {"retrieval": {"documents_retrieved": 1}}},
            request_id=kwargs["request_id"],
        )

    monkeypatch.setattr("app.services.retrieval_service.query_kmrag", fake_query)
    _index_doc(seed)
    h = auth("admin_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    session_id = s.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       headers=h, json={"message": "What is the dealer incentive?"})
    msg = resp.get_json()["data"]["assistant_message"]
    assert msg["answer_mode"] == "document_rag"
    assert msg["sources"][0]["document_name"] == "Hero.pdf"
    assert msg["sources"][0]["page_number"] == 3

    # Session detail: admin sees KB scope + per-message sources.
    detail = client.get(f"/api/v1/chat/sessions/{session_id}", headers=h).get_json()["data"]
    assert any(m["sources"] for m in detail["messages"] if m["role"] == "assistant")


def test_chat_user_session_detail_hides_kb_metadata(client, auth, seed, monkeypatch, assign_user_kb):
    _mock_openai(monkeypatch)

    def fake_query(**kwargs):
        return KmragQueryResult(
            answer="The dealer incentive is 5%.",
            context_found=True,
            sources=[{"document_name": "Hero.pdf", "page_number": 3, "score": 0.82}],
            metadata={}, request_id=kwargs["request_id"],
        )

    monkeypatch.setattr("app.services.retrieval_service.query_kmrag", fake_query)
    _index_doc(seed)
    assign_user_kb()
    h = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    session_id = s.get_json()["data"]["id"]
    client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                headers=h, json={"message": "What is the dealer incentive?"})

    detail = client.get(f"/api/v1/chat/sessions/{session_id}", headers=h).get_json()["data"]
    assert detail["kb_ids"] == []
    assert detail["kb_names"] == []
    assert all(m["sources"] == [] for m in detail["messages"])


def test_hybrid_fused_scores_still_ground_the_answer(client, auth, seed, monkeypatch, assign_user_kb):
    # Regression: KMRAG hybrid search returns a fused RRF `score` (~0.005-0.016)
    # per source, NOT a cosine similarity. Re-filtering those against
    # RAG_MIN_RELEVANCE_SCORE used to reject every source and silently degrade
    # a grounded answer to the general-knowledge fallback. Sources must be
    # judged on their raw vector_score/bm25_score signals instead.
    _mock_openai(monkeypatch, text="Generic fallback that must NOT be used.")

    def fake_query(**kwargs):
        return KmragQueryResult(
            answer="The products are X100 and X200.",
            context_found=True,
            sources=[
                {"document_name": "Products.pdf", "page_number": 1,
                 "score": 0.0161, "vector_score": 0.3609, "bm25_score": 0.6},
                {"document_name": "Products.pdf", "page_number": 2,
                 "score": 0.0098, "vector_score": 0.3146, "bm25_score": 0.2},
                # Weak on both raw signals: filtered out.
                {"document_name": "Products.pdf", "page_number": 9,
                 "score": 0.0052, "vector_score": 0.2614, "bm25_score": None},
            ],
            metadata={"steps": {"retrieval": {"documents_retrieved": 3}}},
            request_id=kwargs["request_id"],
        )

    monkeypatch.setattr("app.services.retrieval_service.query_kmrag", fake_query)
    _index_doc(seed)
    assign_user_kb()
    h = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    session_id = s.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       headers=h, json={"message": "give me PRODUCTS list"})
    msg = resp.get_json()["data"]["assistant_message"]
    assert msg["answer_mode"] == "document_rag"
    assert msg["message_text"] == "The products are X100 and X200."
    assert {src.page_number for src in _db_sources(msg["id"])} == {1, 2}


def test_qualifies_gate_reads_raw_signals():
    from app.services.chat_service import _qualifies

    # Vector cosine at/above the gate qualifies.
    assert _qualifies({"score": 0.01, "vector_score": 0.36, "bm25_score": None}, 0.35)
    # Any BM25 lexical hit qualifies regardless of vector.
    assert _qualifies({"score": 0.01, "vector_score": 0.20, "bm25_score": 0.1}, 0.35)
    # Weak vector, no BM25: rejected.
    assert not _qualifies({"score": 0.01, "vector_score": 0.20, "bm25_score": None}, 0.35)
    # No raw signals at all: trust KMRAG's own gate (sources are pre-filtered).
    assert _qualifies({"score": 0.9}, 0.35)
    assert _qualifies({}, 0.35)


def test_kb_state_answers_are_never_cached(client, auth, seed, monkeypatch, assign_user_kb):
    # Regression: "Knowledge Base is not ready for chat yet." was cached for the
    # full TTL, so the user kept getting it for up to an hour AFTER indexing
    # finished. KB-state outcomes must never be cached.
    _mock_openai(monkeypatch)
    assign_user_kb()  # assigned KB exists but has no indexed document
    h = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    session_id = s.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       headers=h, json={"message": "lahori murgh tandoori"})
    msg = resp.get_json()["data"]["assistant_message"]
    assert msg["answer_mode"] == "no_document_evidence"

    from app.extensions import redis_client
    assert not [k for k in redis_client.scan_iter("tenant:*:chat_answer:*")]


def _set_rag_only(seed):
    from app.constants import RagMode
    from app.models.tenant import Tenant

    tenant = db.session.get(Tenant, seed["tenant_a"])
    tenant.rag_mode = RagMode.RAG_ONLY
    db.session.commit()


def test_no_context_falls_back_to_disclosed_general_in_rag_first(client, auth, seed, monkeypatch, assign_user_kb):
    # Retrieval-first: the KBs are searched, find nothing, and rag_first (default)
    # falls back to a general answer instead of a dead end.
    _mock_openai(monkeypatch)

    def fake_query(**kwargs):
        return KmragQueryResult(answer="", context_found=False, sources=[],
                                metadata={}, request_id=kwargs["request_id"])

    monkeypatch.setattr("app.services.retrieval_service.query_kmrag", fake_query)
    _index_doc(seed)
    assign_user_kb()
    h = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    session_id = s.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       headers=h, json={"message": "According to the document, what is X?"})
    msg = resp.get_json()["data"]["assistant_message"]
    assert msg["answer_mode"] == "normal"  # general fallback, disclosed via prompt
    assert msg["sources"] == []


def test_hindi_query_realigns_english_rag_answer(client, auth, seed, monkeypatch, assign_user_kb):
    # Reply-language contract: a Hindi query whose grounded KMRAG answer comes
    # back in English must be re-rendered in Hindi by the chatbot-side
    # alignment pass (the mocked OpenAI call), while staying document_rag.
    hindi_answer = "डीलर इंसेंटिव 5% है।"
    _mock_openai(monkeypatch, text=hindi_answer)

    def fake_query(**kwargs):
        return KmragQueryResult(
            answer="The dealer incentive is 5%.",
            context_found=True,
            sources=[{"document_name": "Hero.pdf", "page_number": 3, "score": 0.82}],
            metadata={"steps": {"retrieval": {"documents_retrieved": 1}}},
            request_id=kwargs["request_id"],
        )

    monkeypatch.setattr("app.services.retrieval_service.query_kmrag", fake_query)
    _index_doc(seed)
    assign_user_kb()
    h = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    session_id = s.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       headers=h, json={"message": "डीलर इंसेंटिव कितना है?"})
    assert resp.status_code == 200
    msg = resp.get_json()["data"]["assistant_message"]
    assert msg["answer_mode"] == "document_rag"
    assert msg["message_text"] == hindi_answer
    from app.models.chat_message import ChatMessage
    row = db.session.get(ChatMessage, msg["id"])
    assert row.retrieval_metadata["reply_language"] == "Hindi"
    assert row.retrieval_metadata["language_aligned"] is True


def test_english_query_keeps_rag_answer_unaligned(client, auth, seed, monkeypatch, assign_user_kb):
    # No language mismatch → the KMRAG answer must pass through untouched,
    # with no alignment LLM call (mocked OpenAI would corrupt the text).
    _mock_openai(monkeypatch, text="MUST NOT REPLACE THE GROUNDED ANSWER")

    def fake_query(**kwargs):
        return KmragQueryResult(
            answer="The dealer incentive is 5%.",
            context_found=True,
            sources=[{"document_name": "Hero.pdf", "page_number": 3, "score": 0.82}],
            metadata={"steps": {"retrieval": {"documents_retrieved": 1}}},
            request_id=kwargs["request_id"],
        )

    monkeypatch.setattr("app.services.retrieval_service.query_kmrag", fake_query)
    _index_doc(seed)
    assign_user_kb()
    h = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    session_id = s.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       headers=h, json={"message": "What is the dealer incentive?"})
    msg = resp.get_json()["data"]["assistant_message"]
    assert msg["message_text"] == "The dealer incentive is 5%."
    from app.models.chat_message import ChatMessage
    row = db.session.get(ChatMessage, msg["id"])
    assert row.retrieval_metadata["language_aligned"] is False


def test_no_context_in_rag_only_returns_not_found(client, auth, seed, monkeypatch, assign_user_kb):
    _mock_openai(monkeypatch)
    _set_rag_only(seed)

    def fake_query(**kwargs):
        return KmragQueryResult(answer="", context_found=False, sources=[],
                                metadata={}, request_id=kwargs["request_id"])

    monkeypatch.setattr("app.services.retrieval_service.query_kmrag", fake_query)
    _index_doc(seed)
    assign_user_kb()
    h = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    session_id = s.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       headers=h, json={"message": "According to the document, what is X?"})
    msg = resp.get_json()["data"]["assistant_message"]
    assert msg["answer_mode"] == "no_document_evidence"
    assert "could not find" in msg["message_text"].lower()
    assert msg["sources"] == []


def test_unindexed_kb_chat_gets_not_ready_message_per_turn(client, auth, seed, monkeypatch, assign_user_kb):
    # An assigned KB with no confirmed indexed documents is not chat-ready yet.
    # Session creation still succeeds instantly; the first message returns a
    # clean "not ready" answer and KMRAG is never called.
    _mock_openai(monkeypatch)
    called = {"kmrag": False}

    def fake_query(**kwargs):
        called["kmrag"] = True
        raise AssertionError("KMRAG should not be called for an un-indexed KB")

    monkeypatch.setattr("app.services.retrieval_service.query_kmrag", fake_query)
    assign_user_kb()
    h = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    assert s.status_code == 201
    session_id = s.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       headers=h, json={"message": "What is the dealer incentive?"})
    msg = resp.get_json()["data"]["assistant_message"]
    assert msg["answer_mode"] == "no_document_evidence"
    assert "not ready" in msg["message_text"].lower()
    assert called["kmrag"] is False


def test_rag_kmrag_rejection_degrades_cleanly(client, auth, seed, monkeypatch, assign_user_kb):
    # If KMRAG rejects (e.g. doc queued but not yet ingested): rag_first falls
    # back to general; rag_only returns a clean transient message. Neither is a 500.
    from app.integrations.kmrag_client import KmragQueryRejected

    _mock_openai(monkeypatch)
    _index_doc(seed, status=DocumentStatus.COMPLETED)

    def fake_query(**kwargs):
        raise KmragQueryRejected("not accessible for this tenant")

    monkeypatch.setattr("app.services.retrieval_service.query_kmrag", fake_query)
    assign_user_kb()
    h = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    session_id = s.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       headers=h, json={"message": "According to the document, what is X?"})
    assert resp.status_code == 200
    msg = resp.get_json()["data"]["assistant_message"]
    assert msg["answer_mode"] == "normal"  # rag_first general fallback

    _set_rag_only(seed)
    s2 = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    session2 = s2.get_json()["data"]["id"]
    resp2 = client.post(f"/api/v1/chat/sessions/{session2}/messages",
                        headers=h, json={"message": "According to the document, what is X?"})
    assert resp2.status_code == 200
    msg2 = resp2.get_json()["data"]["assistant_message"]
    assert msg2["answer_mode"] == "no_document_evidence"
    assert "unavailable" in msg2["message_text"].lower()


def test_definition_question_hits_rag_first(client, auth, seed, monkeypatch, assign_user_kb):
    """The reported bug: 'What is Acknowledgement Statement?' has no document-y
    phrasing, but retrieval must still run FIRST — routing by phrasing skipped
    RAG entirely. Also verifies the KMRAG request_id is the stable session id."""
    _mock_openai(monkeypatch)
    seen = {"request_ids": [], "calls": 0}

    def fake_query(**kwargs):
        seen["calls"] += 1
        seen["request_ids"].append(kwargs["request_id"])
        return KmragQueryResult(
            answer="An Acknowledgement Statement is the scripted confirmation ...",
            context_found=True,
            sources=[{"document_name": "Script.pdf", "page_number": 2, "score": 0.9}],
            metadata={}, request_id=kwargs["request_id"],
        )

    monkeypatch.setattr("app.services.retrieval_service.query_kmrag", fake_query)
    _index_doc(seed)
    assign_user_kb()
    h = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    session_id = s.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       headers=h, json={"message": "What is Acknowledgement Statement?"})
    msg = resp.get_json()["data"]["assistant_message"]
    assert msg["answer_mode"] == "document_rag"
    assert _db_sources(msg["id"])[0].document_name == "Script.pdf"
    assert seen["calls"] == 1
    # Stable conversation id -> KMRAG's own caches / history can work.
    assert seen["request_ids"] == [session_id]


def test_repeated_identical_query_served_from_cache(client, auth, seed, monkeypatch, assign_user_kb):
    """Second identical message in the same conversation: no KMRAG call, no new
    LLM call, identical answer text, sources preserved."""
    _mock_openai(monkeypatch, text="Title Words")
    calls = {"kmrag": 0}

    def fake_query(**kwargs):
        calls["kmrag"] += 1
        return KmragQueryResult(
            answer="The dealer incentive is 5%.", context_found=True,
            sources=[{"document_name": "Hero.pdf", "page_number": 3, "score": 0.82}],
            metadata={}, request_id=kwargs["request_id"],
        )

    monkeypatch.setattr("app.services.retrieval_service.query_kmrag", fake_query)
    _index_doc(seed)
    assign_user_kb()
    h = auth("user_a@x.com")
    s = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    session_id = s.get_json()["data"]["id"]

    first = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                        headers=h, json={"message": "What is the dealer incentive?"})
    second = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                         headers=h, json={"message": "  what is THE dealer incentive?  "})  # normalized match

    m1 = first.get_json()["data"]["assistant_message"]
    m2 = second.get_json()["data"]["assistant_message"]
    assert calls["kmrag"] == 1  # second answer came from the chat answer cache
    assert m1["message_text"] == m2["message_text"]
    # Cache replay still persists the source rows (for admin review).
    assert _db_sources(m2["id"])[0].document_name == "Hero.pdf"
    assert m2["total_tokens"] == 0 and float(m2["estimated_cost_usd"]) == 0

    # A different conversation must NOT share the cached answer (session-scoped).
    s2 = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    other = s2.get_json()["data"]["id"]
    client.post(f"/api/v1/chat/sessions/{other}/messages",
                headers=h, json={"message": "What is the dealer incentive?"})
    assert calls["kmrag"] == 2


def test_cannot_select_other_tenant_kb(client, auth, seed):
    h = auth("user_a@x.com")
    resp = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": [seed["kb_b"]]})
    assert resp.status_code == 403
    assert "cannot select knowledge bases" in resp.get_json()["error"]["message"].lower()


def test_chat_user_without_kb_assignment_starts_session_immediately(client, auth, seed):
    # Unassigned Chat Users automatically search all tenant KBs, and 'Start a
    # New Chat' must never block — readiness is reported per-message instead.
    h = auth("user_a@x.com")
    resp = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": []})
    assert resp.status_code == 201
    assert resp.get_json()["data"]["id"]


def test_chat_user_cannot_manually_select_even_assigned_kb(client, auth, seed, assign_user_kb):
    assign_user_kb()
    h = auth("user_a@x.com")
    resp = client.post("/api/v1/chat/sessions", headers=h, json={"kb_ids": [seed["kb_a"]]})
    assert resp.status_code == 403
    assert "cannot select knowledge bases" in resp.get_json()["error"]["message"].lower()


def test_super_admin_cannot_create_chat_session(client, auth, seed):
    # Super Admin has no tenant; chat is tenant-scoped -> clean 403, not a 500.
    resp = client.post("/api/v1/chat/sessions", headers=auth("root@x.com"), json={"title": "test", "kb_ids": []})
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "no_tenant_for_chat"
