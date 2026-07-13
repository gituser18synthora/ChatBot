from __future__ import annotations

from app.extensions import db
from app.models.base import GUID, uuid_pk


class KnowledgeBaseAssignment(db.Model):
    """Grants a tenant read/chat access to a Knowledge Base it does not own.

    Used for the Super Tenant's shared KB library: the KB stays owned + ingested
    by the Super Tenant (in KMRAG), and assignments grant specific tenants the
    right to select and query it. At retrieval time the backend queries KMRAG
    using the KB's OWNER tenant id (KMRAG isolation is by owner), authorized here.
    """

    __tablename__ = "knowledge_base_assignments"

    id = uuid_pk()
    kb_id = db.Column(GUID(), db.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    # The grantee tenant (NOT the owner).
    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by = db.Column(GUID(), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("kb_id", "tenant_id", name="uq_kb_assignment"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kb_id": self.kb_id,
            "tenant_id": self.tenant_id,
            "assigned_by": self.assigned_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
