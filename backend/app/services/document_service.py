"""Document upload orchestration + lifecycle.

Flow (see spec §10): create `pending` record -> `uploading` -> call KMRAG ->
`processing` (KMRAG is async and never confirms completion) or `failed`.

We NEVER mark a document `completed` on our own — KMRAG provides no completion
signal today (documented limitation). Delete is soft-only because KMRAG exposes
no vector-delete endpoint.
"""
from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.constants import AuditAction, DocumentStatus, KBStatus
from app.extensions import db
from app.integrations.kmrag_client import (
    KmragConflict,
    KmragUnavailable,
    delete_kb_file,
    ensure_kmrag_available,
    get_kb_files,
    upload_document_to_kmrag,
)
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.services import audit_service
from app.utils.file_utils import validate_upload
from app.utils.logging_utils import get_request_id
from app.utils.response_utils import ApiError, not_found
from app.utils.uuid_utils import new_uuid

logger = logging.getLogger(__name__)


def reconcile_kb_documents(kb_id: str) -> int:
    """Reconcile a KB's in-flight documents against KMRAG's ingestion status.

    KMRAG ingests asynchronously and writes a kb_files row when a document is
    fully indexed. We poll that (read-only) and move in-flight documents:
      processing/uploading  -> completed  (file present in KMRAG)
      processing/uploading  -> failed     (still absent after the timeout)

    Best-effort: if KMRAG status can't be fetched, nothing changes. Returns the
    number of documents updated.
    """
    from datetime import timedelta

    in_flight = {DocumentStatus.UPLOADING, DocumentStatus.PROCESSING}
    candidates = Document.query.filter(
        Document.kb_id == kb_id,
        Document.upload_status.in_(list(in_flight)),
        Document.deleted_at.is_(None),
    ).all()
    from app.services import kb_service

    if not candidates:
        kb = KnowledgeBase.query.get(kb_id)
        if kb is not None:
            kb_service.refresh_kb_status(kb, commit=True)
        return 0

    kb = KnowledgeBase.query.get(kb_id)
    if kb is None:
        return 0

    files = get_kb_files(tenant_id=kb.tenant_id, kb_id=kb_id)
    if files is None:
        kb_service.refresh_kb_status(kb, kmrag_unavailable=True, commit=True)
        return 0  # status unavailable -> leave everything unchanged

    by_name: dict[str, dict] = {}
    for f in files:
        name = f.get("file_name")
        if name:
            by_name[name] = f  # last write wins (KMRAG keeps one row per name)

    timeout = timedelta(minutes=int(current_app.config["DOCUMENT_PROCESSING_TIMEOUT_MINUTES"]))
    now = datetime.utcnow()
    updated = 0

    for doc in candidates:
        indexed = by_name.get(doc.original_filename)
        if indexed is not None and indexed.get("chunk_count", 0) > 0:
            if doc.upload_status != DocumentStatus.COMPLETED:
                doc.upload_status = DocumentStatus.COMPLETED
                doc.processed_at = now
                doc.ingestion_error = None
                updated += 1
        elif doc.upload_status in in_flight:
            started = doc.uploaded_at or doc.created_at or now
            if now - started > timeout:
                doc.upload_status = DocumentStatus.FAILED
                doc.ingestion_error = (
                    f"Ingestion did not complete within {timeout.seconds // 60 or int(current_app.config['DOCUMENT_PROCESSING_TIMEOUT_MINUTES'])} "
                    "minutes. The document may be unsupported or the ingestion worker may be down. Please retry."
                )
                updated += 1

    if updated:
        kb_service.refresh_kb_status(kb)
        db.session.commit()
        logger.info("reconciled kb=%s documents_updated=%s", kb_id, updated)
    else:
        kb_service.refresh_kb_status(kb, commit=True)
    return updated


def list_documents(kb_id: str, page: int, per_page: int, status: str | None = None, search: str | None = None):
    # Best-effort status reconciliation so the list reflects real ingestion state.
    try:
        reconcile_kb_documents(kb_id)
    except Exception as exc:  # never let reconciliation break the listing
        db.session.rollback()
        logger.warning("reconcile failed kb=%s: %s", kb_id, exc)

    q = Document.query.filter(Document.kb_id == kb_id, Document.upload_status != DocumentStatus.DELETED)
    if status:
        q = q.filter(Document.upload_status == status)
    if search:
        q = q.filter(Document.original_filename.ilike(f"%{search}%"))
    q = q.order_by(Document.created_at.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return items, total


def get_document(document_id: str) -> Document:
    doc = Document.query.get(document_id)
    if not doc or doc.upload_status == DocumentStatus.DELETED:
        raise not_found("The requested document was not found.")
    return doc


def queryable_kb_ids(kb_ids: list[str]) -> list[str]:
    """Return the subset of kb_ids that KMRAG can actually be queried for.

    KMRAG only becomes safe to query after a document is confirmed indexed.
    `processing` means KMRAG accepted the upload but has not confirmed chunks
    yet, so it is deliberately not queryable. Order is preserved.
    """
    if not kb_ids:
        return []
    for kb_id in dict.fromkeys(kb_ids):
        try:
            reconcile_kb_documents(kb_id)
        except Exception as exc:
            db.session.rollback()
            logger.warning("queryable reconciliation failed kb=%s: %s", kb_id, exc)
    rows = (
        db.session.query(Document.kb_id)
        .join(KnowledgeBase, KnowledgeBase.id == Document.kb_id)
        .filter(
            Document.kb_id.in_(kb_ids),
            Document.upload_status == DocumentStatus.COMPLETED,
            KnowledgeBase.status == KBStatus.READY,
        )
        .distinct()
        .all()
    )
    ready = {r[0] for r in rows}
    return [kb_id for kb_id in kb_ids if kb_id in ready]


def _persist_temp(file_storage) -> tuple[str, int]:
    """Stream the upload to a temp file, returning (path, size_bytes).

    Falls back to the system temp dir if the configured dir is not writable, so
    a misconfigured/read-only UPLOAD_TMP_DIR never silently breaks uploads.
    """
    target_dir = current_app.config["UPLOAD_TMP_DIR"]
    try:
        os.makedirs(target_dir, exist_ok=True)
        # Confirm it is actually writable (mount perms, disk full, etc.).
        if not os.access(target_dir, os.W_OK):
            raise PermissionError(target_dir)
    except (OSError, PermissionError) as exc:
        fallback = tempfile.gettempdir()
        logger.warning("UPLOAD_TMP_DIR %r unusable (%s); falling back to %s", target_dir, exc, fallback)
        target_dir = fallback
    fd, path = tempfile.mkstemp(dir=target_dir)
    os.close(fd)
    file_storage.save(path)
    return path, os.path.getsize(path)


def _safe_uuid(value) -> str | None:
    from app.utils.uuid_utils import is_valid_uuid
    return value if is_valid_uuid(value) else None


def _kb_name_from_filename(filename: str) -> str:
    base = os.path.splitext(os.path.basename(filename))[0].strip()
    return (base or "Untitled Knowledge Base")[:200]


def _active_document_for_filename(kb: KnowledgeBase, filename: str) -> Document | None:
    doc = Document.query.filter_by(
        tenant_id=kb.tenant_id,
        kb_id=kb.id,
        active_file_key=filename,
    ).first()
    if doc:
        return doc
    # Compatibility for rows created before active_file_key existed or before
    # the migration was applied in a long-running dev database.
    return (
        Document.query.filter(
            Document.tenant_id == kb.tenant_id,
            Document.kb_id == kb.id,
            Document.original_filename == filename,
            Document.upload_status != DocumentStatus.DELETED,
            Document.deleted_at.is_(None),
        )
        .order_by(Document.created_at.desc())
        .first()
    )


def _assert_kb_can_accept(kb: KnowledgeBase, filename: str) -> None:
    """Enforce the one-document-per-KB rule.

    A Knowledge Base holds exactly one document. Re-uploading the SAME file
    name is the retry/replace path and stays allowed; any other active
    document in the KB blocks the upload.
    """
    other = (
        Document.query.filter(
            Document.kb_id == kb.id,
            Document.upload_status != DocumentStatus.DELETED,
            Document.deleted_at.is_(None),
            Document.original_filename != filename,
        )
        .order_by(Document.created_at.desc())
        .first()
    )
    if other:
        raise ApiError(
            "A Knowledge Base can contain only one document, and this one already "
            f'contains "{other.original_filename}". Create a new Knowledge Base to '
            "upload this file, or delete the existing document first.",
            409,
            "kb_single_document",
        )


def _prepare_document_for_upload(
    kb: KnowledgeBase,
    *,
    filename: str,
    content_type: str,
    size_bytes: int,
    actor_id: str,
) -> Document:
    _assert_kb_can_accept(kb, filename)
    existing = _active_document_for_filename(kb, filename)
    if existing:
        if existing.upload_status == DocumentStatus.COMPLETED:
            raise ApiError(
                "This file is already indexed in this Knowledge Base. Delete it first if you want to replace it.",
                409,
                "document_already_indexed",
            )
        if existing.upload_status in {DocumentStatus.UPLOADING, DocumentStatus.PROCESSING}:
            raise ApiError(
                "This file is already being indexed. Please wait for it to finish before uploading it again.",
                409,
                "document_already_processing",
            )
        # Failed/pending rows are retryable. Reuse the same row so a retry cannot
        # become a second visible/indexed document with the same file name.
        existing.original_filename = filename
        existing.active_file_key = filename
        existing.content_type = content_type
        existing.file_size_bytes = size_bytes
        existing.upload_status = DocumentStatus.UPLOADING
        existing.ingestion_error = None
        existing.kmrag_request_id = None
        existing.kmrag_document_id = None
        existing.uploaded_by = actor_id
        existing.uploaded_at = datetime.utcnow()
        existing.processed_at = None
        existing.deleted_at = None
        return existing

    return Document(
        id=new_uuid(),
        tenant_id=kb.tenant_id,
        kb_id=kb.id,
        original_filename=filename,
        active_file_key=filename,
        content_type=content_type,
        file_size_bytes=size_bytes,
        upload_status=DocumentStatus.UPLOADING,
        uploaded_by=actor_id,
        uploaded_at=datetime.utcnow(),
    )


def upload_document(kb: KnowledgeBase, file_storage, actor_id: str) -> Document:
    # Connectivity first: if KMRAG is down, stop before any validation or row
    # creation so the client sees ONLY the service error (raises 503).
    ensure_kmrag_available()
    if kb.status == KBStatus.INACTIVE:
        raise ApiError("This knowledge base is inactive. Activate it before uploading.", 409, "kb_inactive")

    filename = (file_storage.filename or "").strip()
    request_id = get_request_id()
    if not filename:
        raise ApiError("No file was provided.", 422, "no_file")

    # Save first so we know the true size, then validate.
    tmp_path, size_bytes = _persist_temp(file_storage)
    logger.info(
        "upload received request_id=%s tenant=%s kb=%s file=%r size=%s actor=%s",
        request_id, kb.tenant_id, kb.id, filename, size_bytes, actor_id,
    )
    try:
        content_type = validate_upload(
            filename, size_bytes,
            current_app.config["ALLOWED_FILE_EXTENSIONS"],
            current_app.config["MAX_CONTENT_LENGTH"],
        )
        return _upload_validated_temp(
            kb=kb,
            filename=filename[:500],
            content_type=content_type,
            size_bytes=size_bytes,
            tmp_path=tmp_path,
            actor_id=actor_id,
            request_id=request_id,
        )
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def create_kb_and_upload_document(
    tenant_id: str,
    file_storage,
    actor_id: str,
    kb_name: str | None = None,
    description: str | None = None,
) -> tuple[KnowledgeBase, Document]:
    """Create a fresh KB and upload one document into it.

    This is the explicit "new KB per document" path. It validates the file
    before creating the KB, so bad uploads do not leave empty KB rows behind.
    """
    # Connectivity first: a down KMRAG must not leave an orphan KB + failed
    # document row behind (raises 503 before anything is created).
    ensure_kmrag_available()
    filename = (file_storage.filename or "").strip()
    request_id = get_request_id()
    if not filename:
        raise ApiError("No file was provided.", 422, "no_file")

    tmp_path, size_bytes = _persist_temp(file_storage)
    logger.info(
        "new-kb upload received request_id=%s tenant=%s file=%r size=%s actor=%s",
        request_id, tenant_id, filename, size_bytes, actor_id,
    )
    try:
        content_type = validate_upload(
            filename, size_bytes,
            current_app.config["ALLOWED_FILE_EXTENSIONS"],
            current_app.config["MAX_CONTENT_LENGTH"],
        )
        from app.services import kb_service

        kb = kb_service.create_kb(
            tenant_id,
            {
                "kb_name": (kb_name or _kb_name_from_filename(filename)).strip()[:200],
                "description": description or None,
            },
            actor_id,
        )
        logger.info(
            "new-kb upload created kb request_id=%s tenant=%s kb=%s file=%r",
            request_id, tenant_id, kb.id, filename,
        )
        doc = _upload_validated_temp(
            kb=kb,
            filename=filename[:500],
            content_type=content_type,
            size_bytes=size_bytes,
            tmp_path=tmp_path,
            actor_id=actor_id,
            request_id=request_id,
        )
        return kb, doc
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _upload_validated_temp(
    *,
    kb: KnowledgeBase,
    filename: str,
    content_type: str,
    size_bytes: int,
    tmp_path: str,
    actor_id: str,
    request_id: str,
) -> Document:
    doc: Document | None = None
    try:
        doc = _prepare_document_for_upload(
            kb,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            actor_id=actor_id,
        )
        db.session.add(doc)
        from app.services import kb_service
        kb_service.mark_kb_processing(kb)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise ApiError(
                "This file already exists in this Knowledge Base. Refresh the page before retrying.",
                409,
                "document_duplicate",
            )

        try:
            result = upload_document_to_kmrag(
                tenant_id=kb.tenant_id,
                kb_id=kb.id,
                kb_name=kb.kb_name,
                file_path=tmp_path,
                original_filename=filename,
                content_type=content_type,
                request_id=request_id,
            )
        except (KmragConflict, KmragUnavailable) as exc:
            _mark_failed(doc, str(exc))
            logger.warning("upload failed (kmrag) request_id=%s doc=%s: %s", request_id, doc.id, exc)
            raise

        # KMRAG queued it (async). It is now processing; no completion signal.
        doc.upload_status = DocumentStatus.PROCESSING
        doc.kmrag_request_id = _safe_uuid(result.request_id)
        doc.kmrag_document_id = (result.document_id or None)
        kb_service.refresh_kb_status(kb)
        db.session.commit()
        logger.info("upload queued request_id=%s doc=%s kmrag_status=%r", request_id, doc.id, result.status)

        audit_service.log_action(
            action=AuditAction.DOCUMENT_UPLOADED, entity_type="document", entity_id=doc.id,
            tenant_id=kb.tenant_id, user_id=actor_id, new_data=doc.to_dict(),
        )
        return doc
    except (KmragConflict, KmragUnavailable):
        # Already failure-marked above; let the error handler map to 409/503
        # with KMRAG's safe message. Must precede the generic Exception handler.
        raise
    except ApiError:
        # Validation/business errors already carry a safe message. If a doc row
        # was created, mark it failed so it never lingers in `uploading`.
        if doc is not None and doc.upload_status not in (DocumentStatus.FAILED,):
            _mark_failed(doc, "Upload rejected during validation.")
        raise
    except IntegrityError:
        db.session.rollback()
        raise ApiError(
            "This file already exists in this Knowledge Base. Refresh the page before retrying.",
            409,
            "document_duplicate",
        )
    except Exception as exc:
        # Any unexpected failure (DB, storage, serialization): capture it on the
        # doc if we have one, log with the request_id, and surface a safe error.
        logger.error("upload unexpected error request_id=%s: %s", request_id, exc, exc_info=True)
        if doc is not None:
            _mark_failed(doc, "The document could not be processed. Please retry.")
        raise ApiError("The document could not be uploaded. Please try again.", 500, "upload_failed")


def _mark_failed(doc: Document, message: str) -> None:
    try:
        db.session.rollback()
        fresh = db.session.get(Document, doc.id)
        if fresh is not None:
            fresh.upload_status = DocumentStatus.FAILED
            fresh.ingestion_error = (message or "")[:2000]
            kb = db.session.get(KnowledgeBase, fresh.kb_id)
            if kb is not None:
                from app.services import kb_service
                kb_service.mark_kb_failed(kb, message)
            db.session.commit()
    except Exception:  # never let failure-marking mask the original error
        db.session.rollback()


def retry_document(document_id: str, file_storage, actor_id: str) -> Document:
    """Retry a failed document. Requires the file to be re-supplied (KMRAG has no
    server-side retry queue we can trigger)."""
    doc = get_document(document_id)
    if doc.upload_status not in DocumentStatus.RETRYABLE:
        raise ApiError("Only failed documents can be retried.", 409, "not_retryable")
    retry_filename = (file_storage.filename or "").strip()[:500]
    if retry_filename and retry_filename != doc.original_filename:
        raise ApiError("Retry this document with the same file name.", 422, "filename_mismatch")
    kb = KnowledgeBase.query.get(doc.kb_id)
    if not kb:
        raise not_found("The requested knowledge base was not found.")

    audit_service.log_action(
        action=AuditAction.DOCUMENT_RETRY, entity_type="document", entity_id=doc.id,
        tenant_id=doc.tenant_id, user_id=actor_id,
    )
    # Reuse the upload path for a fresh attempt.
    return upload_document(kb, file_storage, actor_id)


def delete_document(document_id: str, actor_id: str) -> bool:
    """Soft-delete the document record AND remove its vectors from KMRAG.

    The record is kept (marked deleted) for audit/reversibility, and KMRAG is
    asked to delete the document's chunks so it is excluded from retrieval.
    KMRAG deletion is best-effort: returns True if KMRAG confirmed removal,
    False if KMRAG couldn't be reached (the soft-delete still applies; the doc
    won't be queried because it's no longer `completed`/`processing`).
    """
    doc = get_document(document_id)
    old = doc.to_dict()

    # doc.tenant_id is the KB's OWNER tenant (what KMRAG stores).
    kmrag_removed = delete_kb_file(
        tenant_id=doc.tenant_id, kb_id=doc.kb_id, file_name=doc.original_filename,
    )

    doc.upload_status = DocumentStatus.DELETED
    doc.active_file_key = None
    doc.deleted_at = datetime.utcnow()
    if not kmrag_removed:
        doc.ingestion_error = (
            "Removed from the console. Vector cleanup in the retrieval engine "
            "could not be confirmed and will need a retry if the engine was down."
        )
    audit_service.log_action(
        action=AuditAction.DOCUMENT_DELETED, entity_type="document", entity_id=doc.id,
        tenant_id=doc.tenant_id, user_id=actor_id,
        old_data=old, new_data={**doc.to_dict(), "kmrag_removed": kmrag_removed}, commit=False,
    )
    from app.services import kb_service
    kb = db.session.get(KnowledgeBase, doc.kb_id)
    if kb is not None:
        kb_service.refresh_kb_status(kb)
    db.session.commit()
    return kmrag_removed
