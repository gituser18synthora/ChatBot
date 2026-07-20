"""Document-ingestion usage capture (tokens + cost per document, per tenant)."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from app.constants import DocumentStatus, RequestType
from app.extensions import db
from app.models.document import Document
from app.models.usage_log import UsageLog
from app.services import analytics_service, document_service
from app.utils.uuid_utils import new_uuid


def _make_doc(seed, name, status=DocumentStatus.PROCESSING, age_minutes=1):
    doc = Document(
        id=new_uuid(), tenant_id=seed["tenant_a"], kb_id=seed["kb_a"],
        original_filename=name, active_file_key=name, content_type="application/pdf",
        file_size_bytes=10, upload_status=status,
        uploaded_at=datetime.utcnow() - timedelta(minutes=age_minutes),
    )
    db.session.add(doc)
    db.session.commit()
    return doc


def _kmrag_file(name, tokens=1500, cost=0.00012735, chunks=12):
    # Mirrors KMRAG's /kb/{kb_id}/files shape. total_tokens/total_cost_usd cover
    # embedding + OCR + LLM structuring; embedding_cost_usd is the embedding slice.
    return {
        "file_name": name, "chunk_count": chunks, "total_tokens": tokens,
        "embedding_cost_usd": 0.00003, "total_cost_usd": cost,
        "processing_time_ms": 900, "uploaded_at": None,
    }


def _usage_rows(tenant_id):
    return UsageLog.query.filter_by(
        tenant_id=tenant_id, request_type=RequestType.DOCUMENT_INGESTION
    ).all()


def test_ingestion_usage_recorded_on_completion(client, auth, seed, monkeypatch):
    doc = _make_doc(seed, "hero.pdf")
    monkeypatch.setattr(
        "app.services.document_service.get_kb_files",
        lambda **k: [_kmrag_file("hero.pdf")],
    )
    document_service.reconcile_kb_documents(seed["kb_a"])

    refreshed = db.session.get(Document, doc.id)
    assert refreshed.upload_status == "completed"
    assert refreshed.ingestion_total_tokens == 1500
    assert Decimal(str(refreshed.ingestion_cost_usd)) == Decimal("0.00012735")

    rows = _usage_rows(seed["tenant_a"])
    assert len(rows) == 1
    row = rows[0]
    # The whole ingestion total, and KMRAG's cost taken verbatim.
    assert row.total_tokens == 1500
    assert Decimal(str(row.total_cost_usd)) == Decimal("0.00012735")
    # Document tokens must NOT pollute the query input/output split.
    assert row.input_tokens == 0
    assert row.output_tokens == 0


def test_ingestion_usage_is_billed_once(client, auth, seed, monkeypatch):
    _make_doc(seed, "hero.pdf")
    monkeypatch.setattr(
        "app.services.document_service.get_kb_files",
        lambda **k: [_kmrag_file("hero.pdf")],
    )
    # Reconcile runs on every documents-page load — it must never re-bill.
    document_service.reconcile_kb_documents(seed["kb_a"])
    document_service.reconcile_kb_documents(seed["kb_a"])
    document_service.reconcile_kb_documents(seed["kb_a"])

    rows = _usage_rows(seed["tenant_a"])
    assert len(rows) == 1


def test_already_completed_document_is_backfilled(client, auth, seed, monkeypatch):
    # Indexed before usage tracking existed: no in-flight status to trigger on.
    doc = _make_doc(seed, "old.pdf", status=DocumentStatus.COMPLETED)
    assert doc.ingestion_total_tokens is None
    monkeypatch.setattr(
        "app.services.document_service.get_kb_files",
        lambda **k: [_kmrag_file("old.pdf", tokens=800, cost=0.00005)],
    )
    document_service.reconcile_kb_documents(seed["kb_a"])

    assert db.session.get(Document, doc.id).ingestion_total_tokens == 800
    assert len(_usage_rows(seed["tenant_a"])) == 1


def test_no_usage_reported_leaves_document_unbilled(client, auth, seed, monkeypatch):
    # KMRAG reports the file but no token/cost numbers -> don't lock in a zero;
    # stay NULL so a later reconcile can still bill it.
    doc = _make_doc(seed, "nousage.pdf")
    monkeypatch.setattr(
        "app.services.document_service.get_kb_files",
        lambda **k: [{"file_name": "nousage.pdf", "chunk_count": 3}],
    )
    document_service.reconcile_kb_documents(seed["kb_a"])

    refreshed = db.session.get(Document, doc.id)
    assert refreshed.upload_status == "completed"
    assert refreshed.ingestion_total_tokens is None
    assert _usage_rows(seed["tenant_a"]) == []


def test_kmrag_unavailable_bills_nothing(client, auth, seed, monkeypatch):
    doc = _make_doc(seed, "x.pdf")
    monkeypatch.setattr("app.services.document_service.get_kb_files", lambda **k: None)
    document_service.reconcile_kb_documents(seed["kb_a"])

    assert db.session.get(Document, doc.id).ingestion_total_tokens is None
    assert _usage_rows(seed["tenant_a"]) == []


def test_zero_total_cost_falls_back_to_embedding_cost(client, auth, seed, monkeypatch):
    # Deployed KMRAG builds populate embedding_cost_usd but leave total_cost_usd
    # at 0. Billing the document at $0 despite real spend would be wrong.
    _make_doc(seed, "old-build.pdf")
    monkeypatch.setattr(
        "app.services.document_service.get_kb_files",
        lambda **k: [{
            "file_name": "old-build.pdf", "chunk_count": 56,
            "total_tokens": 8157, "embedding_cost_usd": 0.000163,
            "total_cost_usd": 0.0,
        }],
    )
    document_service.reconcile_kb_documents(seed["kb_a"])

    rows = _usage_rows(seed["tenant_a"])
    assert len(rows) == 1
    assert rows[0].total_tokens == 8157
    assert Decimal(str(rows[0].total_cost_usd)) == Decimal("0.000163")


def test_analytics_reports_document_usage_tenant_wise_and_overall(
    client, auth, seed, monkeypatch,
):
    _make_doc(seed, "a.pdf")
    _make_doc(seed, "b.pdf")
    monkeypatch.setattr(
        "app.services.document_service.get_kb_files",
        lambda **k: [
            _kmrag_file("a.pdf", tokens=1000, cost=0.0001),
            _kmrag_file("b.pdf", tokens=500, cost=0.00005),
        ],
    )
    document_service.reconcile_kb_documents(seed["kb_a"])

    # Tenant-scoped view.
    tokens = analytics_service.token_breakdown(seed["tenant_a"])
    assert tokens["document_tokens"] == 1500
    assert tokens["total_tokens"] == 1500
    # Ingestion must not leak into the query input/output split.
    assert tokens["input_tokens"] == 0
    assert tokens["output_tokens"] == 0
    assert tokens["document_cost_usd"] == 0.00015

    # Overall (all-tenant) view sees the same usage.
    overall = analytics_service.token_breakdown(None)
    assert overall["document_tokens"] == 1500

    costs = analytics_service.cost_breakdown(seed["tenant_a"])
    assert costs["document_ingestions"] == 2

    kb = analytics_service.kb_usage(seed["tenant_a"], seed["kb_a"])
    assert kb["ingestion_tokens"] == 1500
    assert kb["ingestion_cost_usd"] == 0.00015
