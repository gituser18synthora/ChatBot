from __future__ import annotations

import io

from app.integrations.kmrag_client import KmragUnavailable, KmragUploadResult


def _upload(client, headers, kb_id, filename="doc.pdf", data=b"%PDF-1.4 test"):
    return client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents/upload",
        headers=headers,
        data={"file": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )


def _upload_new_kb(client, headers, tenant_id, filename="doc.pdf", data=b"%PDF-1.4 test"):
    return client.post(
        f"/api/v1/tenants/{tenant_id}/knowledge-bases/documents/upload",
        headers=headers,
        data={"file": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )


def test_upload_success_marks_processing(client, auth, seed, monkeypatch):
    def fake_upload(**kwargs):
        return KmragUploadResult(ok=True, status="queued", kb_id=kwargs["kb_id"],
                                 file_name=kwargs["original_filename"], request_id=kwargs["request_id"])

    monkeypatch.setattr("app.services.document_service.upload_document_to_kmrag", fake_upload)
    resp = _upload(client, auth("admin_a@x.com"), seed["kb_a"])
    assert resp.status_code == 201
    assert resp.get_json()["data"]["upload_status"] == "processing"
    from app.models.knowledge_base import KnowledgeBase
    assert KnowledgeBase.query.get(seed["kb_a"]).status == "processing"


def test_second_document_in_same_kb_is_rejected(client, auth, seed, monkeypatch):
    # One-document-per-KB rule: a KB holds exactly one document; another file
    # must go into a new KB.
    monkeypatch.setattr(
        "app.services.document_service.upload_document_to_kmrag",
        lambda **k: KmragUploadResult(ok=True, status="queued", kb_id=k["kb_id"],
                                      file_name=k["original_filename"], request_id=k["request_id"]),
    )
    headers = auth("admin_a@x.com")
    assert _upload(client, headers, seed["kb_a"], filename="one.pdf").status_code == 201
    second = _upload(client, headers, seed["kb_a"], filename="two.pdf")
    assert second.status_code == 409
    assert second.get_json()["error"]["code"] == "kb_single_document"

    from app.models.document import Document
    docs = Document.query.filter(
        Document.kb_id == seed["kb_a"], Document.upload_status != "deleted"
    ).all()
    assert [d.original_filename for d in docs] == ["one.pdf"]


def test_kb_accepts_new_document_after_delete(client, auth, seed, monkeypatch):
    # Deleting the KB's document frees the slot for a different file.
    monkeypatch.setattr(
        "app.services.document_service.upload_document_to_kmrag",
        lambda **k: KmragUploadResult(ok=True, status="queued", kb_id=k["kb_id"],
                                      file_name=k["original_filename"], request_id=k["request_id"]),
    )
    monkeypatch.setattr("app.services.document_service.delete_kb_file", lambda **k: True)
    headers = auth("admin_a@x.com")
    assert _upload(client, headers, seed["kb_a"], filename="one.pdf").status_code == 201

    from app.models.document import Document
    doc = Document.query.filter_by(kb_id=seed["kb_a"], original_filename="one.pdf").one()
    assert client.delete(f"/api/v1/documents/{doc.id}", headers=headers).status_code == 200
    assert _upload(client, headers, seed["kb_a"], filename="two.pdf").status_code == 201


def test_new_kb_upload_generates_distinct_kb_per_document(client, auth, seed, monkeypatch):
    monkeypatch.setattr(
        "app.services.document_service.upload_document_to_kmrag",
        lambda **k: KmragUploadResult(ok=True, status="queued", kb_id=k["kb_id"],
                                      file_name=k["original_filename"], request_id=k["request_id"]),
    )
    headers = auth("admin_a@x.com")

    first = _upload_new_kb(client, headers, seed["tenant_a"], filename="one.pdf")
    second = _upload_new_kb(client, headers, seed["tenant_a"], filename="two.pdf")

    assert first.status_code == 201
    assert second.status_code == 201
    first_doc = first.get_json()["data"]["document"]
    second_doc = second.get_json()["data"]["document"]
    assert first_doc["kb_id"] != second_doc["kb_id"]

    from app.models.document import Document
    assert Document.query.filter_by(kb_id=first_doc["kb_id"]).count() == 1
    assert Document.query.filter_by(kb_id=second_doc["kb_id"]).count() == 1


def test_upload_rejects_unsupported_type(client, auth, seed, monkeypatch):
    monkeypatch.setattr("app.services.document_service.upload_document_to_kmrag", lambda **k: None)
    resp = _upload(client, auth("admin_a@x.com"), seed["kb_a"], filename="virus.exe")
    assert resp.status_code == 422


def _kmrag_down(monkeypatch):
    def down():
        raise KmragUnavailable("KMRAG service is not running. Please start KMRAG and retry document upload.")
    monkeypatch.setattr("app.services.document_service.ensure_kmrag_available", down)


def test_upload_stops_at_kmrag_precheck_leaves_no_rows(client, auth, seed, monkeypatch):
    # KMRAG down at the connectivity pre-check: only the service error, and no
    # document row is created (so no misleading "KB already has its document"
    # state appears afterwards).
    _kmrag_down(monkeypatch)
    resp = _upload(client, auth("admin_a@x.com"), seed["kb_a"])
    assert resp.status_code == 503
    assert "KMRAG service is not running" in resp.get_json()["error"]["message"]
    from app.models.document import Document
    assert Document.query.filter_by(kb_id=seed["kb_a"]).count() == 0


def test_new_kb_upload_stops_at_kmrag_precheck_creates_no_kb(client, auth, seed, monkeypatch):
    _kmrag_down(monkeypatch)
    from app.models.document import Document
    from app.models.knowledge_base import KnowledgeBase
    kb_count = KnowledgeBase.query.count()
    doc_count = Document.query.count()

    resp = _upload_new_kb(client, auth("admin_a@x.com"), seed["tenant_a"])
    assert resp.status_code == 503
    assert "KMRAG service is not running" in resp.get_json()["error"]["message"]
    assert KnowledgeBase.query.count() == kb_count  # no orphan KB
    assert Document.query.count() == doc_count


def test_upload_kmrag_failure_marks_failed(client, auth, seed, monkeypatch):
    def boom(**kwargs):
        raise KmragUnavailable("temporarily unavailable")

    monkeypatch.setattr("app.services.document_service.upload_document_to_kmrag", boom)
    resp = _upload(client, auth("admin_a@x.com"), seed["kb_a"])
    assert resp.status_code == 503
    # The document row should be recorded as failed.
    from app.models.document import Document
    from app.models.knowledge_base import KnowledgeBase
    doc = Document.query.filter_by(kb_id=seed["kb_a"]).first()
    assert doc.upload_status == "failed"
    kb = KnowledgeBase.query.get(seed["kb_a"])
    assert kb.status == "failed"
    assert "temporarily unavailable" in (kb.status_message or "")


def test_retry_same_filename_reuses_failed_row_without_duplicate(client, auth, seed, monkeypatch):
    calls = {"count": 0}

    def flaky_upload(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise KmragUnavailable("KMRAG service is not running.")
        return KmragUploadResult(ok=True, status="queued", kb_id=kwargs["kb_id"],
                                 file_name=kwargs["original_filename"], request_id=kwargs["request_id"])

    monkeypatch.setattr("app.services.document_service.upload_document_to_kmrag", flaky_upload)
    headers = auth("admin_a@x.com")

    first = _upload(client, headers, seed["kb_a"], filename="same.pdf")
    assert first.status_code == 503

    from app.models.document import Document
    failed = Document.query.filter_by(kb_id=seed["kb_a"], original_filename="same.pdf").one()
    assert failed.upload_status == "failed"

    second = _upload(client, headers, seed["kb_a"], filename="same.pdf")
    assert second.status_code == 201
    assert second.get_json()["data"]["id"] == failed.id
    assert second.get_json()["data"]["upload_status"] == "processing"

    visible = Document.query.filter(
        Document.kb_id == seed["kb_a"],
        Document.original_filename == "same.pdf",
        Document.upload_status != "deleted",
    ).all()
    assert [doc.id for doc in visible] == [failed.id]


def test_duplicate_completed_file_upload_is_rejected(client, auth, seed, monkeypatch):
    monkeypatch.setattr(
        "app.services.document_service.upload_document_to_kmrag",
        lambda **k: KmragUploadResult(ok=True, status="queued", kb_id=k["kb_id"],
                                      file_name=k["original_filename"], request_id=k["request_id"]),
    )
    headers = auth("admin_a@x.com")
    assert _upload(client, headers, seed["kb_a"], filename="same.pdf").status_code == 201

    from app.constants import DocumentStatus
    from app.extensions import db
    from app.models.document import Document
    doc = Document.query.filter_by(kb_id=seed["kb_a"], original_filename="same.pdf").one()
    doc.upload_status = DocumentStatus.COMPLETED
    db.session.commit()

    duplicate = _upload(client, headers, seed["kb_a"], filename="same.pdf")
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"]["code"] == "document_already_indexed"
    assert Document.query.filter_by(kb_id=seed["kb_a"], original_filename="same.pdf").count() == 1


def test_upload_no_file_part_is_clean_422(client, auth, seed):
    # A request with no 'file' part (the classic boundary-less symptom).
    resp = client.post(
        f"/api/v1/knowledge-bases/{seed['kb_a']}/documents/upload",
        headers=auth("admin_a@x.com"),
        data={},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "validation_error"


def test_upload_tolerates_non_uuid_request_id_header(client, auth, seed, monkeypatch):
    # A proxy-injected non-UUID X-Request-ID must not break the CHAR(36) column.
    def fake_upload(**kwargs):
        # KMRAG echoes back whatever request_id we passed; it may be a UUID here.
        return KmragUploadResult(ok=True, status="queued", kb_id=kwargs["kb_id"],
                                 file_name=kwargs["original_filename"], request_id="not-a-uuid-" + "x" * 60)

    monkeypatch.setattr("app.services.document_service.upload_document_to_kmrag", fake_upload)
    headers = {**auth("admin_a@x.com"), "X-Request-ID": "some/proxy-id-that-is-way-too-long-and-not-a-uuid"}
    resp = client.post(
        f"/api/v1/knowledge-bases/{seed['kb_a']}/documents/upload",
        headers=headers,
        data={"file": (io.BytesIO(b"%PDF-1.4"), "x.pdf")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    from app.models.document import Document
    doc = Document.query.filter_by(kb_id=seed["kb_a"]).first()
    assert doc.upload_status == "processing"
    assert doc.kmrag_request_id is None  # invalid id stored as NULL, not truncated


def test_chat_user_cannot_upload(client, auth, seed, monkeypatch):
    monkeypatch.setattr("app.services.document_service.upload_document_to_kmrag", lambda **k: None)
    resp = _upload(client, auth("user_a@x.com"), seed["kb_a"])
    assert resp.status_code == 403


def _seed_upload(client, auth, seed, monkeypatch):
    monkeypatch.setattr(
        "app.services.document_service.upload_document_to_kmrag",
        lambda **k: KmragUploadResult(ok=True, status="queued", kb_id=k["kb_id"],
                                      file_name=k["original_filename"], request_id=k["request_id"]),
    )
    _upload(client, auth("admin_a@x.com"), seed["kb_a"])
    from app.models.document import Document
    return Document.query.filter_by(kb_id=seed["kb_a"]).first()


def test_delete_removes_from_kmrag(client, auth, seed, monkeypatch):
    doc = _seed_upload(client, auth, seed, monkeypatch)
    calls = {}
    def fake_delete(**k):
        calls.update(k)
        return True  # KMRAG confirmed removal
    monkeypatch.setattr("app.services.document_service.delete_kb_file", fake_delete)
    resp = client.delete(f"/api/v1/documents/{doc.id}", headers=auth("admin_a@x.com"))
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert "note" not in body
    assert "deleted from the retrieval engine" in body["message"]
    # KMRAG was called with the KB owner tenant + the document's filename.
    assert calls["kb_id"] == seed["kb_a"] and calls["tenant_id"] == seed["tenant_a"]
    from app.models.document import Document
    assert Document.query.get(doc.id).upload_status == "deleted"


def test_delete_soft_when_kmrag_unreachable(client, auth, seed, monkeypatch):
    doc = _seed_upload(client, auth, seed, monkeypatch)
    monkeypatch.setattr("app.services.document_service.delete_kb_file", lambda **k: False)
    resp = client.delete(f"/api/v1/documents/{doc.id}", headers=auth("admin_a@x.com"))
    assert resp.status_code == 200
    assert "note" in resp.get_json()["data"]  # honest: vector cleanup unconfirmed
    from app.models.document import Document
    assert Document.query.get(doc.id).upload_status == "deleted"
