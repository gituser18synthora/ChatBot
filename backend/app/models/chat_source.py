from __future__ import annotations

from app.extensions import db
from app.models.base import GUID, uuid_pk


class ChatSource(db.Model):
    """A citation attached to an assistant message.

    Populated only from real KMRAG retrieval output. Fields KMRAG does not
    currently return (chunk_id, document_id, source_text_preview) stay NULL —
    we never fabricate them.
    """

    __tablename__ = "chat_sources"

    id = uuid_pk()
    message_id = db.Column(GUID(), db.ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    kb_id = db.Column(GUID(), db.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=True, index=True)

    document_id = db.Column(GUID(), nullable=True)
    document_name = db.Column(db.String(500), nullable=True)
    page_number = db.Column(db.Integer, nullable=True)
    chunk_id = db.Column(db.String(120), nullable=True)
    relevance_score = db.Column(db.Numeric(8, 4), nullable=True)
    source_text_preview = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kb_id": self.kb_id,
            "kb_name": getattr(self, "_kb_name", None),
            "document_id": self.document_id,
            "document_name": self.document_name,
            "page_number": self.page_number,
            "chunk_id": self.chunk_id,
            "relevance_score": float(self.relevance_score) if self.relevance_score is not None else None,
            "source_text_preview": self.source_text_preview,
        }
