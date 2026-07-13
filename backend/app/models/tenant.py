from __future__ import annotations

from app.constants import RagMode, TenantStatus
from app.extensions import db
from app.models.base import GUID, TimestampMixin, uuid_pk


class Tenant(TimestampMixin, db.Model):
    __tablename__ = "tenants"

    id = uuid_pk()
    tenant_name = db.Column(db.String(200), nullable=False)
    tenant_code = db.Column(db.String(80), nullable=False, unique=True, index=True)
    status = db.Column(db.String(20), nullable=False, default=TenantStatus.ACTIVE, index=True)
    # A single "Super Tenant" owns the shared KB library and can grant its KBs to
    # other tenants (see KnowledgeBaseAssignment). Managed by the Super User.
    is_super_tenant = db.Column(db.Boolean, nullable=False, default=False, index=True)
    # Answering policy for this tenant's chats: 'rag_first' (general AI allowed
    # for clearly general questions) or 'rag_only' (KB answers only).
    rag_mode = db.Column(db.String(20), nullable=False, default=RagMode.DEFAULT,
                         server_default=RagMode.DEFAULT)
    contact_name = db.Column(db.String(200), nullable=True)
    contact_email = db.Column(db.String(255), nullable=True)
    # Soft delete: the row is retained for audit/reference; excluded from lists.
    deleted_at = db.Column(db.DateTime, nullable=True)

    knowledge_bases = db.relationship("KnowledgeBase", backref="tenant", lazy="dynamic")
    users = db.relationship("User", backref="tenant", lazy="dynamic")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_name": self.tenant_name,
            "tenant_code": self.tenant_code,
            "status": self.status,
            "is_super_tenant": self.is_super_tenant,
            "rag_mode": self.rag_mode or RagMode.DEFAULT,
            "contact_name": self.contact_name,
            "contact_email": self.contact_email,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
