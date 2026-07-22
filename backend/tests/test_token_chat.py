"""Token-authenticated chat API (opaque user_token, not JWT chat)."""
from __future__ import annotations

from app.extensions import db
from app.integrations.kmrag_client import KmragQueryResult
from app.models.user_token import UserToken
from app.utils.uuid_utils import new_uuid


def _store_token(seed, kb_ids=None):
    token = "a" * 32
    row = UserToken(
        id=new_uuid(),
        user_id=seed["user_a"],
        tenant_id=seed["tenant_a"],
        kb_ids=kb_ids if kb_ids is not None else [seed["kb_a"]],
        token=token,
        created_by=seed["admin_a"],
    )
    db.session.add(row)
    db.session.commit()
    return token


def _headers(token: str) -> dict:
    return {"X-Access-Token": token}


def test_token_chat_success(client, seed, monkeypatch):
    token = _store_token(seed)
    monkeypatch.setattr(
        "app.services.token_chat_service.document_service.queryable_kb_ids",
        lambda ids: list(ids),
    )
    monkeypatch.setattr(
        "app.services.token_chat_service.retrieval_service.validate_kbs_for_tenant",
        lambda tenant_id, kb_ids: None,
    )
    monkeypatch.setattr(
        "app.services.token_chat_service.retrieval_service.retrieve",
        lambda **kwargs: KmragQueryResult(
            answer="Grounded answer",
            context_found=True,
            sources=[],
            metadata={},
            request_id=kwargs["request_id"],
        ),
    )

    resp = client.post(
        "/api/v1/token-chat",
        headers=_headers(token),
        json={"session_id": "sess-1", "query": "What is leave policy?"},
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["answer"] == "Grounded answer"
    assert data["session_id"] == "sess-1"
    assert data["context_found"] is True
    assert data["user_id"] == seed["user_a"]
    assert data["tenant_id"] == seed["tenant_a"]
    assert data["kb_ids"] == [seed["kb_a"]]


def test_token_chat_passes_session_id_as_request_id(client, seed, monkeypatch):
    token = _store_token(seed)
    seen = {}

    monkeypatch.setattr(
        "app.services.token_chat_service.document_service.queryable_kb_ids",
        lambda ids: list(ids),
    )
    monkeypatch.setattr(
        "app.services.token_chat_service.retrieval_service.validate_kbs_for_tenant",
        lambda tenant_id, kb_ids: None,
    )

    def _retrieve(**kwargs):
        seen.update(kwargs)
        return KmragQueryResult(
            answer="ok", context_found=True, sources=[], metadata={}, request_id=kwargs["request_id"],
        )

    monkeypatch.setattr(
        "app.services.token_chat_service.retrieval_service.retrieve", _retrieve,
    )

    client.post(
        "/api/v1/token-chat",
        headers=_headers(token),
        json={"session_id": "conv-abc", "query": "hello"},
    )
    assert seen["request_id"] == "conv-abc"
    assert seen["tenant_id"] == seed["tenant_a"]
    assert seen["user_id"] == seed["user_a"]
    assert seen["kb_ids"] == [seed["kb_a"]]
    assert seen["query"] == "hello"


def test_token_chat_rejects_invalid_token(client, seed):
    resp = client.post(
        "/api/v1/token-chat",
        headers=_headers("b" * 32),
        json={"session_id": "s1", "query": "hi"},
    )
    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "unauthorized"


def test_token_chat_rejects_missing_header(client, seed):
    resp = client.post(
        "/api/v1/token-chat",
        json={"session_id": "s1", "query": "hi"},
    )
    assert resp.status_code == 401


def test_token_chat_no_queryable_kbs(client, seed, monkeypatch):
    token = _store_token(seed)
    monkeypatch.setattr(
        "app.services.token_chat_service.document_service.queryable_kb_ids",
        lambda ids: [],
    )
    resp = client.post(
        "/api/v1/token-chat",
        headers=_headers(token),
        json={"session_id": "s1", "query": "hi"},
    )
    assert resp.status_code == 200
    assert "not ready" in resp.get_json()["data"]["answer"].lower()
