from __future__ import annotations

from app.constants import DocumentStatus
from app.extensions import db
from app.models.base import GUID, TimestampMixin, uuid_pk


class Document(TimestampMixin, db.Model):
    __tablename__ = "documents"
    __table_args__ = (
        # One active visible row per file name in a KB. Deleted/superseded rows
        # clear active_file_key so history can remain without blocking re-upload.
        db.UniqueConstraint("tenant_id", "kb_id", "active_file_key", name="uq_documents_active_file"),
    )

    id = uuid_pk()
    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    kb_id = db.Column(GUID(), db.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)

    original_filename = db.Column(db.String(500), nullable=False)
    active_file_key = db.Column(db.String(500), nullable=True)
    content_type = db.Column(db.String(120), nullable=True)
    file_size_bytes = db.Column(db.BigInteger, nullable=False, default=0)

    upload_status = db.Column(db.String(20), nullable=False, default=DocumentStatus.PENDING, index=True)
    # KMRAG is async and returns no document id today; kept nullable for a future
    # KMRAG status/callback endpoint.
    kmrag_document_id = db.Column(db.String(120), nullable=True)
    kmrag_request_id = db.Column(GUID(), nullable=True)
    ingestion_error = db.Column(db.Text, nullable=True)

    uploaded_by = db.Column(GUID(), nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=True)
    processed_at = db.Column(db.DateTime, nullable=True)
    deleted_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "kb_id": self.kb_id,
            "original_filename": self.original_filename,
            "content_type": self.content_type,
            "file_size_bytes": self.file_size_bytes,
            "upload_status": self.upload_status,
            "ingestion_error": self.ingestion_error,
            "uploaded_by": self.uploaded_by,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
