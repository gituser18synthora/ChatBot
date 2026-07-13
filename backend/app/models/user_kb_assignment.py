from __future__ import annotations

from app.extensions import db
from app.models.base import GUID, uuid_pk


class UserKnowledgeBaseAssignment(db.Model):
    """Scopes a single user's chat retrieval to specific Knowledge Bases.

Semantics (see chat retrieval):
  - A user WITH one or more rows here may only chat against those KBs.
  - A Chat User WITHOUT rows has no KB access.
  - A Tenant Admin WITHOUT rows falls back to ALL of their tenant's accessible
    KBs (owned + shared).

    Each assigned KB must be accessible to the user's tenant (owned by the tenant
    or shared to it via a Super Tenant KnowledgeBaseAssignment). This table is
    per-user; the tenant-level Super Tenant sharing table is separate.
    """

    __tablename__ = "user_knowledge_base_assignments"

    id = uuid_pk()
    user_id = db.Column(
        GUID(), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kb_id = db.Column(
        GUID(), db.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_by = db.Column(GUID(), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "kb_id", name="uq_user_kb_assignment"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "kb_id": self.kb_id,
            "assigned_by": self.assigned_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
