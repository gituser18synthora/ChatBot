"""Usage / cost analytics aggregations from MySQL (source of truth)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func

from app.constants import DocumentStatus, RequestType, Role, TenantStatus
from app.extensions import db
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.tenant import Tenant
from app.models.usage_log import UsageLog
from app.models.user import User


def _scope(query, model, tenant_id: str | None):
    return query.filter(model.tenant_id == tenant_id) if tenant_id else query


def _to_float(v) -> float:
    return float(v) if v is not None else 0.0


def dashboard(tenant_id: str | None) -> dict:
    today = date.today()
    month_start = today.replace(day=1)

    tenants_q = Tenant.query.filter(Tenant.deleted_at.is_(None))
    if tenant_id:
        tenants_q = tenants_q.filter(Tenant.id == tenant_id)

    total_tenants = tenants_q.count()
    active_tenants = tenants_q.filter(Tenant.status == TenantStatus.ACTIVE).count()

    kb_q = _scope(KnowledgeBase.query, KnowledgeBase, tenant_id)
    doc_q = _scope(Document.query, Document, tenant_id).filter(Document.upload_status != DocumentStatus.DELETED)
    user_q = (_scope(User.query, User, tenant_id) if tenant_id else User.query).filter(User.deleted_at.is_(None))
    session_q = _scope(ChatSession.query, ChatSession, tenant_id).filter(ChatSession.deleted_at.is_(None))

    today_cost = _scope(
        db.session.query(func.coalesce(func.sum(UsageLog.total_cost_usd), 0)), UsageLog, tenant_id
    ).filter(func.date(UsageLog.created_at) == today).scalar()
    month_cost = _scope(
        db.session.query(func.coalesce(func.sum(UsageLog.total_cost_usd), 0)), UsageLog, tenant_id
    ).filter(UsageLog.created_at >= month_start).scalar()
    today_tokens = _scope(
        db.session.query(func.coalesce(func.sum(UsageLog.total_tokens), 0)), UsageLog, tenant_id
    ).filter(func.date(UsageLog.created_at) == today).scalar()

    return {
        "total_tenants": total_tenants,
        "active_tenants": active_tenants,
        "total_knowledge_bases": kb_q.count(),
        "total_documents": doc_q.count(),
        "documents_processing": doc_q.filter(Document.upload_status == DocumentStatus.PROCESSING).count(),
        "failed_documents": doc_q.filter(Document.upload_status == DocumentStatus.FAILED).count(),
        "total_users": user_q.count(),
        "total_conversations": session_q.count(),
        "today_token_usage": int(today_tokens or 0),
        "today_openai_cost": _to_float(today_cost),
        "monthly_openai_cost": _to_float(month_cost),
    }


def cost_breakdown(tenant_id: str | None, days: int = 30) -> dict:
    since = datetime.utcnow() - timedelta(days=days)
    base = _scope(db.session.query(UsageLog), UsageLog, tenant_id).filter(UsageLog.created_at >= since)

    by_day = (
        base.with_entities(
            func.date(UsageLog.created_at).label("day"),
            func.coalesce(func.sum(UsageLog.total_cost_usd), 0),
            func.coalesce(func.sum(UsageLog.total_tokens), 0),
        )
        .group_by("day").order_by("day").all()
    )
    by_model = (
        base.with_entities(
            UsageLog.model_name,
            func.coalesce(func.sum(UsageLog.total_cost_usd), 0),
            func.coalesce(func.sum(UsageLog.total_tokens), 0),
        )
        .group_by(UsageLog.model_name).all()
    )
    by_type = (
        base.with_entities(UsageLog.request_type, func.count())
        .group_by(UsageLog.request_type).all()
    )

    result = {
        "daily": [{"day": str(d), "cost_usd": _to_float(c), "tokens": int(t or 0)} for d, c, t in by_day],
        "by_model": [{"model": m, "cost_usd": _to_float(c), "tokens": int(t or 0)} for m, c, t in by_model],
        "rag_queries": sum(n for rt, n in by_type if rt == RequestType.CHAT_RAG),
        "general_queries": sum(n for rt, n in by_type if rt == RequestType.CHAT_GENERAL),
    }

    # Cost by tenant is only meaningful for a super-admin (all-tenant) view.
    if tenant_id is None:
        by_tenant = (
            base.with_entities(
                UsageLog.tenant_id, func.coalesce(func.sum(UsageLog.total_cost_usd), 0)
            ).group_by(UsageLog.tenant_id).all()
        )
        names = {t.id: t.tenant_name for t in Tenant.query.all()}
        result["by_tenant"] = [
            {"tenant_id": tid, "tenant_name": names.get(tid), "cost_usd": _to_float(c)}
            for tid, c in by_tenant
        ]
    return result


def token_breakdown(tenant_id: str | None, days: int = 30) -> dict:
    since = datetime.utcnow() - timedelta(days=days)
    base = _scope(db.session.query(UsageLog), UsageLog, tenant_id).filter(UsageLog.created_at >= since)
    row = base.with_entities(
        func.coalesce(func.sum(UsageLog.input_tokens), 0),
        func.coalesce(func.sum(UsageLog.output_tokens), 0),
        func.coalesce(func.sum(UsageLog.total_tokens), 0),
    ).first()
    return {"input_tokens": int(row[0] or 0), "output_tokens": int(row[1] or 0), "total_tokens": int(row[2] or 0)}


def kb_usage(tenant_id: str | None, kb_id: str) -> dict:
    doc_q = Document.query.filter(Document.kb_id == kb_id, Document.upload_status != DocumentStatus.DELETED)
    if tenant_id:
        doc_q = doc_q.filter(Document.tenant_id == tenant_id)
    # RAG messages referencing this KB (from persisted sources).
    from app.models.chat_source import ChatSource
    rag_hits = ChatSource.query.filter(ChatSource.kb_id == kb_id).count()
    return {
        "kb_id": kb_id,
        "document_count": doc_q.count(),
        "processing": doc_q.filter(Document.upload_status == DocumentStatus.PROCESSING).count(),
        "failed": doc_q.filter(Document.upload_status == DocumentStatus.FAILED).count(),
        "citations": rag_hits,
    }
