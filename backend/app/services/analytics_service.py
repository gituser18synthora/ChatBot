"""Usage / cost analytics aggregations from PostgreSQL (source of truth)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

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
from app.services import cost_service


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
        "document_ingestions": sum(
            n for rt, n in by_type if rt == RequestType.DOCUMENT_INGESTION
        ),
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
    """Per-tenant (or all-tenant when tenant_id is None) token + cost breakdown.

    Tokens:
      * input_tokens / output_tokens are QUERY tokens only — document-ingestion
        rows carry their tokens in total_tokens with input/output at 0, so they
        are reported separately as document_tokens. input + output != total
        whenever documents were ingested; document_tokens is the difference.

    Costs:
      * document_cost_usd is KMRAG's real per-file cost, summed.
      * query_cost_usd is the real cost charged for queries (KMRAG's combined
        total for RAG rows + locally-priced general/title rows).
      * input_cost_usd / output_cost_usd split the QUERY cost by token side.
        KMRAG returns one combined total per query (no input/output split), so
        these are priced from local MODEL_PRICING on the query tokens per model.
        They sum to ~query_cost_usd (a tiny gap is the query-embedding slice
        that local pricing doesn't cover).
      * total_cost_usd is the tenant's real overall spend = query + document.
    """
    since = datetime.utcnow() - timedelta(days=days)
    base = _scope(db.session.query(UsageLog), UsageLog, tenant_id).filter(UsageLog.created_at >= since)

    row = base.with_entities(
        func.coalesce(func.sum(UsageLog.input_tokens), 0),
        func.coalesce(func.sum(UsageLog.output_tokens), 0),
        func.coalesce(func.sum(UsageLog.total_tokens), 0),
        func.coalesce(func.sum(UsageLog.total_cost_usd), 0),
    ).first()

    doc = base.filter(
        UsageLog.request_type == RequestType.DOCUMENT_INGESTION
    ).with_entities(
        func.coalesce(func.sum(UsageLog.total_tokens), 0),
        func.coalesce(func.sum(UsageLog.total_cost_usd), 0),
    ).first()

    # Real query spend = overall real spend minus document spend.
    overall_cost = Decimal(str(row[3] or 0))
    document_cost = Decimal(str(doc[1] or 0))
    query_cost = overall_cost - document_cost

    # Input/output cost split: price query tokens per model from local pricing,
    # because KMRAG reports queries as a single combined cost (input/output cost
    # columns are 0 on RAG rows). Grouped by model so mixed models price right.
    by_model = (
        base.filter(UsageLog.request_type != RequestType.DOCUMENT_INGESTION)
        .with_entities(
            UsageLog.model_name,
            func.coalesce(func.sum(UsageLog.input_tokens), 0),
            func.coalesce(func.sum(UsageLog.output_tokens), 0),
        )
        .group_by(UsageLog.model_name)
        .all()
    )
    input_cost = Decimal(0)
    output_cost = Decimal(0)
    for model_name, in_tok, out_tok in by_model:
        costs = cost_service.compute_cost(model_name, int(in_tok or 0), int(out_tok or 0))
        input_cost += costs["input_cost_usd"]
        output_cost += costs["output_cost_usd"]

    return {
        # tokens
        "input_tokens": int(row[0] or 0),
        "output_tokens": int(row[1] or 0),
        "total_tokens": int(row[2] or 0),
        "document_tokens": int(doc[0] or 0),
        # costs
        "input_cost_usd": _to_float(input_cost),
        "output_cost_usd": _to_float(output_cost),
        "query_cost_usd": _to_float(query_cost),
        "document_cost_usd": _to_float(document_cost),
        "total_cost_usd": _to_float(overall_cost),
    }


def kb_usage(tenant_id: str | None, kb_id: str) -> dict:
    doc_q = Document.query.filter(Document.kb_id == kb_id, Document.upload_status != DocumentStatus.DELETED)
    if tenant_id:
        doc_q = doc_q.filter(Document.tenant_id == tenant_id)
    # RAG messages referencing this KB (from persisted sources).
    from app.models.chat_source import ChatSource
    rag_hits = ChatSource.query.filter(ChatSource.kb_id == kb_id).count()

    # What ingesting this KB's documents cost (embedding + OCR + structuring),
    # summed from the per-document totals KMRAG reported.
    totals = doc_q.with_entities(
        func.coalesce(func.sum(Document.ingestion_total_tokens), 0),
        func.coalesce(func.sum(Document.ingestion_cost_usd), 0),
    ).first()

    return {
        "kb_id": kb_id,
        "document_count": doc_q.count(),
        "processing": doc_q.filter(Document.upload_status == DocumentStatus.PROCESSING).count(),
        "failed": doc_q.filter(Document.upload_status == DocumentStatus.FAILED).count(),
        "citations": rag_hits,
        "ingestion_tokens": int(totals[0] or 0),
        "ingestion_cost_usd": _to_float(totals[1]),
    }
