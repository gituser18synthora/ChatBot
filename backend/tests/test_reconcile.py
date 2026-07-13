from __future__ import annotations

from datetime import datetime, timedelta

from app.constants import DocumentStatus
from app.extensions import db
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.services import document_service
from app.utils.uuid_utils import new_uuid


def _make_doc(seed, name, status=DocumentStatus.PROCESSING, age_minutes=1):
    doc = Document(
        id=new_uuid(), tenant_id=seed["tenant_a"], kb_id=seed["kb_a"],
        original_filename=name, active_file_key=name, content_type="application/pdf", file_size_bytes=10,
        upload_status=status, uploaded_at=datetime.utcnow() - timedelta(minutes=age_minutes),
    )
    db.session.add(doc)
    db.session.commit()
    return doc


def test_processing_becomes_indexed_when_kmrag_reports_file(client, auth, seed, monkeypatch):
    doc = _make_doc(seed, "hero.pdf")
    monkeypatch.setattr(
        "app.services.document_service.get_kb_files",
        lambda **k: [{"file_name": "hero.pdf", "chunk_count": 12, "total_tokens": 100}],
    )
    document_service.reconcile_kb_documents(seed["kb_a"])
    assert db.session.get(Document, doc.id).upload_status == "completed"
    assert db.session.get(KnowledgeBase, seed["kb_a"]).status == "ready"


def test_processing_times_out_to_failed(client, auth, seed, monkeypatch):
    doc = _make_doc(seed, "stuck.pdf", age_minutes=999)  # older than the 30m default
    # KMRAG reports no ingested files for this KB.
    monkeypatch.setattr("app.services.document_service.get_kb_files", lambda **k: [])
    document_service.reconcile_kb_documents(seed["kb_a"])
    refreshed = db.session.get(Document, doc.id)
    assert refreshed.upload_status == "failed"
    assert "did not complete" in (refreshed.ingestion_error or "")
    assert db.session.get(KnowledgeBase, seed["kb_a"]).status == "failed"


def test_recent_processing_stays_processing(client, auth, seed, monkeypatch):
    doc = _make_doc(seed, "fresh.pdf", age_minutes=2)
    monkeypatch.setattr("app.services.document_service.get_kb_files", lambda **k: [])
    document_service.reconcile_kb_documents(seed["kb_a"])
    assert db.session.get(Document, doc.id).upload_status == "processing"
    assert db.session.get(KnowledgeBase, seed["kb_a"]).status == "processing"


def test_status_unavailable_leaves_documents_unchanged(client, auth, seed, monkeypatch):
    doc = _make_doc(seed, "x.pdf", age_minutes=999)
    # None => KMRAG status could not be fetched: do not touch anything.
    monkeypatch.setattr("app.services.document_service.get_kb_files", lambda **k: None)
    document_service.reconcile_kb_documents(seed["kb_a"])
    assert db.session.get(Document, doc.id).upload_status == "processing"
    kb = db.session.get(KnowledgeBase, seed["kb_a"])
    assert kb.status == "processing"
    assert "KMRAG service is not running" in (kb.status_message or "")


def test_failed_doc_is_not_silently_recovered_by_same_filename(client, auth, seed, monkeypatch):
    doc = _make_doc(seed, "late.pdf", status=DocumentStatus.FAILED)
    monkeypatch.setattr(
        "app.services.document_service.get_kb_files",
        lambda **k: [{"file_name": "late.pdf", "chunk_count": 5}],
    )
    document_service.reconcile_kb_documents(seed["kb_a"])
    assert db.session.get(Document, doc.id).upload_status == "failed"
    assert db.session.get(KnowledgeBase, seed["kb_a"]).status == "failed"
