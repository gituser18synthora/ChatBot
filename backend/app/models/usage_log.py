from __future__ import annotations

from app.extensions import db
from app.models.base import GUID, uuid_pk


class UsageLog(db.Model):
    """One row per billable OpenAI call. PostgreSQL is the source of truth for cost."""

    __tablename__ = "usage_logs"

    id = uuid_pk()
    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(GUID(), nullable=True, index=True)
    chat_session_id = db.Column(GUID(), nullable=True, index=True)

    request_type = db.Column(db.String(40), nullable=False, index=True)
    model_name = db.Column(db.String(80), nullable=False, index=True)

    input_tokens = db.Column(db.Integer, nullable=False, default=0)
    output_tokens = db.Column(db.Integer, nullable=False, default=0)
    total_tokens = db.Column(db.Integer, nullable=False, default=0)

    # High precision — do not round early.
    input_cost_usd = db.Column(db.Numeric(16, 10), nullable=False, default=0)
    output_cost_usd = db.Column(db.Numeric(16, 10), nullable=False, default=0)
    total_cost_usd = db.Column(db.Numeric(16, 10), nullable=False, default=0)

    latency_ms = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False, index=True)
