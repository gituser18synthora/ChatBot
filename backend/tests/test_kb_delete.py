"""Knowledge Base deletion safety.

Regression coverage for the `documents.kb_id cannot be null` failure: deleting a
KB must never disassociate (nullify) or destroy its documents. A KB that still
holds documents is refused with 409; only an empty KB may be deleted.
"""
from __future__ import annotations

from sqlalchemy import event

from app.constants import DocumentStatus
from app.extensions import db
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.utils.uuid_utils import new_uuid

DELETE_URL = "/api/v1/knowledge-bases/{kb_id}"


def _add_doc(kb_id, tenant_id, *, status=DocumentStatus.PROCESSING, name="doc.pdf"):
    doc = Document(
        id=new_uuid(),
        tenant_id=tenant_id,
        kb_id=kb_id,
        original_filename=name,
        upload_status=status,
        file_size_bytes=1,
    )
    db.session.add(doc)
    db.session.commit()
    return doc


# ── 404 / 400 / cross-tenant ──────────────────────────────────
def test_delete_missing_kb_returns_404(client, auth, seed):
    resp = client.delete(DELETE_URL.format(kb_id=new_uuid()), headers=auth("admin_a@x.com"))
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "not_found"


def test_delete_other_tenants_kb_returns_404(client, auth, seed):
    # Existing convention: cross-tenant access is 404 (never confirm existence).
    resp = client.delete(DELETE_URL.format(kb_id=seed["kb_b"]), headers=auth("admin_a@x.com"))
    assert resp.status_code == 404
    # The other tenant's KB is untouched.
    assert KnowledgeBase.query.get(seed["kb_b"]) is not None


def test_delete_invalid_uuid_returns_controlled_400(client, auth, seed):
    resp = client.delete(DELETE_URL.format(kb_id="not-a-real-uuid"), headers=auth("admin_a@x.com"))
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["success"] is False
    assert body["error"]["code"] == "invalid_kb_id"
    # No SQL / stack trace leaks into the message.
    assert "SELECT" not in body["error"]["message"]


# ── 409 when documents remain ─────────────────────────────────
def test_delete_kb_with_one_document_returns_409(client, auth, seed):
    _add_doc(seed["kb_a"], seed["tenant_a"])
    resp = client.delete(DELETE_URL.format(kb_id=seed["kb_a"]), headers=auth("admin_a@x.com"))
    assert resp.status_code == 409
    error = resp.get_json()["error"]
    assert error["code"] == "KB_HAS_DOCUMENTS"
    assert error["document_count"] == 1
    assert "1 document" in error["message"]
    # KB and document are both untouched.
    assert KnowledgeBase.query.get(seed["kb_a"]) is not None


def test_delete_kb_with_multiple_documents_returns_409(client, auth, seed):
    _add_doc(seed["kb_a"], seed["tenant_a"], name="a.pdf")
    _add_doc(seed["kb_a"], seed["tenant_a"], name="b.pdf")
    _add_doc(seed["kb_a"], seed["tenant_a"], name="c.pdf")
    resp = client.delete(DELETE_URL.format(kb_id=seed["kb_a"]), headers=auth("admin_a@x.com"))
    assert resp.status_code == 409
    error = resp.get_json()["error"]
    assert error["code"] == "KB_HAS_DOCUMENTS"
    assert error["document_count"] == 3
    assert "3 documents" in error["message"]


def test_failed_delete_leaves_documents_unchanged(client, auth, seed):
    doc = _add_doc(seed["kb_a"], seed["tenant_a"])
    resp = client.delete(DELETE_URL.format(kb_id=seed["kb_a"]), headers=auth("admin_a@x.com"))
    assert resp.status_code == 409

    db.session.expire_all()
    refreshed = Document.query.get(doc.id)
    assert refreshed is not None
    # The whole point of the fix: kb_id is NEVER set to NULL.
    assert refreshed.kb_id == seed["kb_a"]
    assert refreshed.upload_status == DocumentStatus.PROCESSING


def test_soft_deleted_documents_do_not_block_delete(client, auth, seed):
    # A KB whose only documents are already soft-deleted counts as empty.
    _add_doc(seed["kb_a"], seed["tenant_a"], status=DocumentStatus.DELETED)
    resp = client.delete(DELETE_URL.format(kb_id=seed["kb_a"]), headers=auth("admin_a@x.com"))
    assert resp.status_code == 200
    assert KnowledgeBase.query.get(seed["kb_a"]) is None


# ── Happy path + idempotency ──────────────────────────────────
def test_delete_empty_kb_succeeds(client, auth, seed):
    resp = client.delete(DELETE_URL.format(kb_id=seed["kb_a"]), headers=auth("admin_a@x.com"))
    assert resp.status_code == 200
    assert resp.get_json()["data"]["message"] == "Knowledge base deleted."
    assert KnowledgeBase.query.get(seed["kb_a"]) is None


def test_repeated_delete_is_a_controlled_404_not_500(client, auth, seed):
    headers = auth("admin_a@x.com")
    first = client.delete(DELETE_URL.format(kb_id=seed["kb_a"]), headers=headers)
    assert first.status_code == 200
    second = client.delete(DELETE_URL.format(kb_id=seed["kb_a"]), headers=headers)
    assert second.status_code == 404  # never an unhandled 500
    assert second.get_json()["success"] is False


def test_super_admin_can_delete_any_tenants_empty_kb(client, auth, seed):
    resp = client.delete(DELETE_URL.format(kb_id=seed["kb_b"]), headers=auth("root@x.com"))
    assert resp.status_code == 200
    assert KnowledgeBase.query.get(seed["kb_b"]) is None


# ── No UPDATE ... SET kb_id = NULL is ever emitted ────────────
def test_delete_attempt_never_emits_kb_id_nullify(client, auth, seed):
    _add_doc(seed["kb_a"], seed["tenant_a"])
    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = db.session.get_bind()
    event.listen(engine, "before_cursor_execute", _record)
    try:
        resp = client.delete(DELETE_URL.format(kb_id=seed["kb_a"]), headers=auth("admin_a@x.com"))
    finally:
        event.remove(engine, "before_cursor_execute", _record)

    assert resp.status_code == 409
    joined = " ".join(statements).lower()
    # The exact failure mode we are guarding against must never occur.
    assert "update documents set kb_id" not in joined
    assert "set kb_id=null" not in joined.replace(" ", "")


# ── Session stays usable after a rollback ─────────────────────
def test_session_usable_after_rollback(client, auth, seed, monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app.services import kb_service

    # Authenticate first — patching log_action would otherwise break login too.
    headers = auth("admin_a@x.com")

    # Force a database error during the delete's audit write.
    def boom(*args, **kwargs):
        raise OperationalError("stmt", {}, Exception("boom"))

    monkeypatch.setattr(kb_service.audit_service, "log_action", boom)

    failed = client.delete(DELETE_URL.format(kb_id=seed["kb_a"]), headers=headers)
    # Controlled response — no SQL / stack trace leaked.
    assert failed.status_code == 503
    body = failed.get_json()
    assert body["success"] is False
    assert "boom" not in body["error"]["message"]
    assert "OperationalError" not in body["error"]["message"]

    # Rollback happened: the KB still exists and the session is usable again.
    monkeypatch.undo()
    assert KnowledgeBase.query.get(seed["kb_a"]) is not None
    ok = client.get(f"/api/v1/tenants/{seed['tenant_a']}/knowledge-bases", headers=headers)
    assert ok.status_code == 200
