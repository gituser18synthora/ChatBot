from __future__ import annotations

from app.constants import KBStatus
from app.extensions import db
from app.models.base import GUID, TimestampMixin, uuid_pk


class KnowledgeBase(TimestampMixin, db.Model):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        # id is already the global kb_id primary key; this explicit tenant+kb_id
        # guard documents the app-level invariant and protects drifted schemas.
        db.UniqueConstraint("tenant_id", "id", name="uq_knowledge_bases_tenant_id_id"),
    )

    # id (kb_id) is globally unique — it is the shared key passed to KMRAG.
    id = uuid_pk()
    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    kb_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default=KBStatus.PENDING, index=True)
    status_message = db.Column(db.Text, nullable=True)
    created_by = db.Column(GUID(), nullable=True)

    documents = db.relationship("Document", backref="knowledge_base", lazy="dynamic")

    def to_dict(self, document_count: int | None = None, status_counts: dict | None = None) -> dict:
        data = {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "kb_name": self.kb_name,
            "description": self.description,
            "status": self.status,
            "status_message": self.status_message,
            "ready": self.status == KBStatus.READY,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if document_count is not None:
            data["document_count"] = document_count
        if status_counts is not None:
            data.update(status_counts)
        return data
