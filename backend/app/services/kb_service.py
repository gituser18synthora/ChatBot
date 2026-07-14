"""Knowledge Base metadata CRUD. KMRAG holds the vectors; MySQL holds metadata.

kb_id (the KnowledgeBase primary key) is globally unique and is the shared key
passed to KMRAG on upload/query.
"""
from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.constants import AuditAction, DocumentStatus, KBStatus
from app.extensions import db
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.services import audit_service
from app.services.redis_service import cache_delete, kb_key
from app.utils.logging_utils import get_request_id
from app.utils.response_utils import (
    bad_request,
    conflict,
    kb_has_documents,
    not_found,
    service_unavailable,
)
from app.utils.uuid_utils import is_valid_uuid, new_uuid

logger = logging.getLogger(__name__)


def _doc_stats(kb_id: str) -> dict[str, int]:
    rows = (
        db.session.query(Document.upload_status, db.func.count(Document.id))
        .filter(Document.kb_id == kb_id, Document.upload_status != DocumentStatus.DELETED)
        .group_by(Document.upload_status)
        .all()
    )
    by_status = {status: count for status, count in rows}
    processing = (
        by_status.get(DocumentStatus.PENDING, 0)
        + by_status.get(DocumentStatus.UPLOADING, 0)
        + by_status.get(DocumentStatus.PROCESSING, 0)
    )
    completed = by_status.get(DocumentStatus.COMPLETED, 0)
    failed = by_status.get(DocumentStatus.FAILED, 0)
    return {
        "document_count": sum(by_status.values()),
        "indexed_count": completed,
        "processing_count": processing,
        "failed_count": failed,
    }


def _doc_count(kb_id: str) -> int:
    return _doc_stats(kb_id)["document_count"]


def _active_doc_count(tenant_id: str, kb_id: str) -> int:
    """Tenant-scoped count of documents that still occupy the KB (soft-deleted
    rows excluded). Used to decide whether a KB may be deleted."""
    return (
        db.session.query(db.func.count(Document.id))
        .filter(
            Document.tenant_id == tenant_id,
            Document.kb_id == kb_id,
            Document.upload_status != DocumentStatus.DELETED,
        )
        .scalar()
        or 0
    )


def _pending_message() -> str:
    return "Upload documents to start indexing this Knowledge Base."


def _processing_message(kmrag_unavailable: bool = False) -> str:
    if kmrag_unavailable:
        return "KMRAG service is not running. Document indexing is still pending."
    return "Document indexing is pending."


def _failed_message(message: str | None = None) -> str:
    return message or "Knowledge Base creation failed. Retry failed documents after KMRAG is available."


def _ready_message(stats: dict[str, int]) -> str:
    if stats["processing_count"]:
        return "Knowledge Base is ready for chat. Some documents are still indexing."
    if stats["failed_count"]:
        return "Knowledge Base is ready for chat. Some documents failed and can be retried."
    return "Knowledge Base is ready for chat."


def refresh_kb_status(
    kb: KnowledgeBase,
    *,
    message: str | None = None,
    kmrag_unavailable: bool = False,
    force: bool = False,
    commit: bool = False,
) -> KnowledgeBase:
    """Derive the safe KB lifecycle status from document/KMRAG state.

    `inactive` is the only manual status. Every other status is derived so a KB
    cannot be marked chat-ready before KMRAG indexing is confirmed.
    """
    if kb.status == KBStatus.INACTIVE and not force:
        return kb

    stats = _doc_stats(kb.id)
    if stats["indexed_count"] > 0:
        next_status = KBStatus.READY
        next_message = message or _ready_message(stats)
    elif stats["processing_count"] > 0:
        next_status = KBStatus.PROCESSING
        next_message = message or _processing_message(kmrag_unavailable)
    elif stats["failed_count"] > 0:
        next_status = KBStatus.FAILED
        next_message = _failed_message(message)
    else:
        next_status = KBStatus.PENDING
        next_message = message or _pending_message()

    changed = kb.status != next_status or kb.status_message != next_message
    kb.status = next_status
    kb.status_message = next_message
    if changed and commit:
        db.session.commit()
        cache_delete(kb_key(kb.tenant_id, kb.id))
    return kb


def mark_kb_processing(kb: KnowledgeBase, message: str | None = None, *, commit: bool = False) -> KnowledgeBase:
    if kb.status != KBStatus.INACTIVE and kb.status != KBStatus.READY:
        kb.status = KBStatus.PROCESSING
        kb.status_message = message or _processing_message()
        if commit:
            db.session.commit()
            cache_delete(kb_key(kb.tenant_id, kb.id))
    return kb


def mark_kb_failed(kb: KnowledgeBase, message: str | None = None, *, commit: bool = False) -> KnowledgeBase:
    if kb.status != KBStatus.INACTIVE:
        refresh_kb_status(kb, message=_failed_message(message), force=True, commit=False)
        if commit:
            db.session.commit()
            cache_delete(kb_key(kb.tenant_id, kb.id))
    return kb


def kb_payload(kb: KnowledgeBase) -> dict:
    stats = _doc_stats(kb.id)
    return kb.to_dict(document_count=stats["document_count"], status_counts=stats)


def refresh_page_statuses(kbs: list[KnowledgeBase]) -> None:
    changed = False
    for kb in kbs:
        if kb.status == KBStatus.INACTIVE:
            continue
        before = (kb.status, kb.status_message)
        refresh_kb_status(kb)
        changed = changed or before != (kb.status, kb.status_message)
    if changed:
        db.session.commit()
        for kb in kbs:
            cache_delete(kb_key(kb.tenant_id, kb.id))


def list_kbs(tenant_id: str, page: int, per_page: int, search: str | None = None, status: str | None = None):
    q = KnowledgeBase.query.filter(KnowledgeBase.tenant_id == tenant_id)
    if search:
        q = q.filter(KnowledgeBase.kb_name.ilike(f"%{search}%"))
    if status:
        q = q.filter(KnowledgeBase.status == status)
    q = q.order_by(KnowledgeBase.created_at.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    refresh_page_statuses(items)
    return items, total


def get_kb(kb_id: str) -> KnowledgeBase:
    # A malformed identifier is a client error (400), not a DB lookup.
    if not is_valid_uuid(kb_id):
        raise bad_request("Please provide a valid Knowledge Base ID.", "invalid_kb_id")
    kb = KnowledgeBase.query.get(kb_id)
    if not kb:
        raise not_found("The requested knowledge base was not found.")
    return kb


def create_kb(tenant_id: str, data: dict, actor_id: str) -> KnowledgeBase:
    # Allow an explicit kb_id (must be a valid, globally-unique UUID) or generate.
    kb_id = data.get("id") or new_uuid()
    if not is_valid_uuid(kb_id):
        raise conflict("Please provide a valid Knowledge Base ID.")
    existing = KnowledgeBase.query.get(kb_id)
    if existing:
        if existing.tenant_id != tenant_id:
            raise conflict("This knowledge base ID already exists. Please use a different Knowledge Base ID.")
        old = existing.to_dict()
        existing.kb_name = data["kb_name"]
        if "description" in data:
            existing.description = data.get("description")
        if data.get("status") == KBStatus.INACTIVE:
            existing.status = KBStatus.INACTIVE
            existing.status_message = "Knowledge Base is inactive."
        else:
            refresh_kb_status(existing, force=True)
        audit_service.log_action(
            action=AuditAction.KB_UPDATED, entity_type="knowledge_base", entity_id=existing.id,
            tenant_id=tenant_id, user_id=actor_id, old_data=old, new_data=existing.to_dict(), commit=False,
        )
        db.session.commit()
        cache_delete(kb_key(existing.tenant_id, existing.id))
        return existing

    requested_status = data.get("status")
    initial_status = KBStatus.INACTIVE if requested_status == KBStatus.INACTIVE else KBStatus.PENDING
    initial_message = (
        "Knowledge Base is inactive."
        if initial_status == KBStatus.INACTIVE
        else _pending_message()
    )

    kb = KnowledgeBase(
        id=kb_id,
        tenant_id=tenant_id,
        kb_name=data["kb_name"],
        description=data.get("description"),
        status=initial_status,
        status_message=initial_message,
        created_by=actor_id,
    )
    db.session.add(kb)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise conflict("This knowledge base ID already exists. Please use a different Knowledge Base ID.")

    audit_service.log_action(
        action=AuditAction.KB_CREATED, entity_type="knowledge_base", entity_id=kb.id,
        tenant_id=tenant_id, user_id=actor_id, new_data=kb.to_dict(), commit=False,
    )
    db.session.commit()
    return kb


def update_kb(kb_id: str, data: dict, actor_id: str) -> KnowledgeBase:
    kb = get_kb(kb_id)
    old = kb.to_dict()
    for field in ("kb_name", "description"):
        if field in data and data[field] is not None:
            setattr(kb, field, data[field])
    if "status" in data and data["status"] is not None:
        if data["status"] == KBStatus.INACTIVE:
            kb.status = KBStatus.INACTIVE
            kb.status_message = "Knowledge Base is inactive."
        else:
            refresh_kb_status(kb, force=True)
    audit_service.log_action(
        action=AuditAction.KB_UPDATED, entity_type="knowledge_base", entity_id=kb.id,
        tenant_id=kb.tenant_id, user_id=actor_id, old_data=old, new_data=kb.to_dict(), commit=False,
    )
    db.session.commit()
    cache_delete(kb_key(kb.tenant_id, kb.id))
    return kb


def delete_kb(kb_id: str, actor_id: str, tenant_scope: str | None = None) -> None:
    """Delete a Knowledge Base, but only when it holds no documents.

    Safety guarantees:
      * Tenant-scoped: a non-super-admin caller (``tenant_scope`` set) can only
        reach their own KB — another tenant's UUID resolves to 404.
      * Never nullifies ``documents.kb_id``. Deletion is refused with 409 while
        any non-deleted document remains, so SQLAlchemy is never asked to run
        ``UPDATE documents SET kb_id = NULL`` (see the KnowledgeBase.documents
        relationship: ``passive_deletes=True``, no delete cascade).
      * Because only an empty KB is ever deleted, there is no per-document data
        left in KMRAG / vector storage to clean up first — the relational
        validation (zero documents) fully precedes any deletion.
    """
    kb = get_kb(kb_id)  # 400 on malformed id, 404 when missing
    # Defense in depth alongside the route's authorization check: reject
    # cross-tenant access at the query layer too (404, never confirm existence).
    if tenant_scope is not None and kb.tenant_id != tenant_scope:
        raise not_found("The requested knowledge base was not found.")

    tenant_id = kb.tenant_id
    document_count = _active_doc_count(tenant_id, kb_id)
    if document_count > 0:
        # Do not delete the KB and do not touch any document's kb_id.
        raise kb_has_documents(document_count)

    old = kb.to_dict()
    try:
        db.session.delete(kb)
        audit_service.log_action(
            action=AuditAction.KB_DELETED, entity_type="knowledge_base", entity_id=kb_id,
            tenant_id=tenant_id, user_id=actor_id, old_data=old, commit=False,
        )
        db.session.commit()
    except IntegrityError:
        # A foreign-key reference we did not guard explicitly. Surface as a
        # controlled 409 — never a raw SQL statement or stack trace.
        db.session.rollback()
        logger.warning(
            "KB delete blocked by integrity constraint request_id=%s kb_id=%s",
            get_request_id(), kb_id,
        )
        raise conflict(
            "This knowledge base is still referenced by other records and cannot be deleted yet."
        )
    except SQLAlchemyError:
        # Any other database failure: roll back so the session stays usable and
        # return a controlled error with no internal details.
        db.session.rollback()
        logger.exception("KB delete failed request_id=%s kb_id=%s", get_request_id(), kb_id)
        raise service_unavailable("The knowledge base could not be deleted. Please try again.")

    cache_delete(kb_key(tenant_id, kb_id))
