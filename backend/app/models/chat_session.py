from __future__ import annotations

from app.extensions import db
from app.models.base import GUID, TimestampMixin, uuid_pk


class ChatSession(TimestampMixin, db.Model):
    __tablename__ = "chat_sessions"

    id = uuid_pk()
    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(GUID(), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    deleted_at = db.Column(db.DateTime, nullable=True)

    messages = db.relationship(
        "ChatMessage", backref="session", lazy="dynamic", cascade="all, delete-orphan"
    )
    kb_links = db.relationship(
        "ChatSessionKnowledgeBase", backref="session", lazy="dynamic", cascade="all, delete-orphan"
    )

    def to_dict(self, kb_ids: list[str] | None = None) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "title": self.title,
            "status": self.status,
            "kb_ids": kb_ids if kb_ids is not None else [link.kb_id for link in self.kb_links],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ChatSessionKnowledgeBase(db.Model):
    """Relationship table: which KBs a chat session is scoped to (multi-select)."""

    __tablename__ = "chat_session_knowledge_bases"

    id = uuid_pk()
    chat_session_id = db.Column(
        GUID(), db.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    kb_id = db.Column(GUID(), db.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("chat_session_id", "kb_id", name="uq_session_kb"),
    )
