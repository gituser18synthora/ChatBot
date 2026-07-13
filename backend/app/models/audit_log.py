from __future__ import annotations

from app.extensions import db
from app.models.base import GUID, uuid_pk


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = uuid_pk()
    tenant_id = db.Column(GUID(), nullable=True, index=True)
    user_id = db.Column(GUID(), nullable=True, index=True)

    action = db.Column(db.String(60), nullable=False, index=True)
    entity_type = db.Column(db.String(60), nullable=True, index=True)
    entity_id = db.Column(GUID(), nullable=True, index=True)

    old_data = db.Column(db.JSON, nullable=True)
    new_data = db.Column(db.JSON, nullable=True)

    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(400), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "old_data": self.old_data,
            "new_data": self.new_data,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
