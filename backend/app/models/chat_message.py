from __future__ import annotations

from app.extensions import db
from app.models.base import GUID, uuid_pk


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = uuid_pk()
    chat_session_id = db.Column(
        GUID(), db.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(GUID(), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    role = db.Column(db.String(20), nullable=False)  # user | assistant | system
    message_text = db.Column(db.Text, nullable=False)
    answer_mode = db.Column(db.String(30), nullable=True)  # normal|document_rag|mixed|no_document_evidence|error

    model_name = db.Column(db.String(80), nullable=True)
    prompt_tokens = db.Column(db.Integer, nullable=False, default=0)
    completion_tokens = db.Column(db.Integer, nullable=False, default=0)
    total_tokens = db.Column(db.Integer, nullable=False, default=0)
    estimated_cost_usd = db.Column(db.Numeric(14, 8), nullable=False, default=0)
    latency_ms = db.Column(db.Integer, nullable=True)
    retrieval_metadata = db.Column(db.JSON, nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False, index=True)

    sources = db.relationship(
        "ChatSource", backref="message", lazy="dynamic", cascade="all, delete-orphan"
    )

    def to_dict(self, include_sources: bool = True) -> dict:
        data = {
            "id": self.id,
            "chat_session_id": self.chat_session_id,
            "role": self.role,
            "message_text": self.message_text,
            "answer_mode": self.answer_mode,
            "model_name": self.model_name,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": float(self.estimated_cost_usd or 0),
            "latency_ms": self.latency_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_sources:
            data["sources"] = [s.to_dict() for s in self.sources]
        return data
