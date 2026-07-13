"""Retrieval orchestration: validate KB access, then call KMRAG.

Authorizes every selected KB (owned by the tenant OR shared with it via a Super
Tenant assignment) and requires it to be ready BEFORE any KMRAG call. Because
KMRAG binds each KB to its OWNER tenant and enforces that on retrieval, queries
are grouped by owner tenant and one KMRAG call is made per group.
"""
from __future__ import annotations

import logging
from collections import defaultdict

from flask import current_app

from app.constants import KBStatus
from app.integrations.kmrag_client import KmragQueryResult, query_kmrag
from app.models.knowledge_base import KnowledgeBase
from app.services import assignment_service
from app.utils.response_utils import ApiError, forbidden, not_found

logger = logging.getLogger(__name__)


def validate_kbs_for_tenant(tenant_id: str, kb_ids: list[str]) -> list[KnowledgeBase]:
    """Return the KB rows for kb_ids, enforcing access (own/shared) + ready."""
    if not kb_ids:
        raise ApiError("Select at least one knowledge base.", 422, "no_kb_selected")
    kbs = KnowledgeBase.query.filter(KnowledgeBase.id.in_(kb_ids)).all()
    found = {kb.id: kb for kb in kbs}
    for kb_id in kb_ids:
        kb = found.get(kb_id)
        if not kb:
            raise not_found("The requested knowledge base was not found.")
        if not assignment_service.is_kb_accessible(tenant_id, kb):
            raise forbidden("The selected knowledge base is not available to your tenant.")
        if kb.status != KBStatus.READY:
            raise ApiError("The selected knowledge base is not ready for chat yet.", 409, "kb_not_ready")
    return list(found.values())


def _owner_groups(kb_ids: list[str]) -> dict[str, list[str]]:
    """Group kb_ids by their OWNER tenant (kb.tenant_id) — the id KMRAG expects."""
    kbs = KnowledgeBase.query.filter(KnowledgeBase.id.in_(kb_ids)).all()
    owner_of = {kb.id: kb.tenant_id for kb in kbs}
    groups: dict[str, list[str]] = defaultdict(list)
    for kb_id in kb_ids:
        owner = owner_of.get(kb_id)
        if owner:
            groups[owner].append(kb_id)
    return groups


def retrieve(
    *,
    tenant_id: str,
    kb_ids: list[str],
    query: str,
    request_id: str,
    user_id: str | None,
) -> KmragQueryResult:
    """Query KMRAG, grouping by owner tenant. `tenant_id` is the requesting
    tenant (already authorized); each KMRAG call uses the KB group's OWNER id."""
    cfg = current_app.config
    groups = _owner_groups(kb_ids)

    # Common case: all selected KBs share one owner -> a single call.
    if len(groups) <= 1:
        owner = next(iter(groups), tenant_id)
        return query_kmrag(
            tenant_id=owner, kb_ids=list(groups.get(owner, kb_ids)), query=query,
            request_id=request_id, user_id=user_id,
            top_k=cfg["RAG_TOP_K"], alpha=cfg["RAG_ALPHA"], model=cfg["KMRAG_QUERY_MODEL"],
        )

    # Mixed owners (tenant's own KBs + KBs shared from the Super Tenant): call each
    # group under its owner and merge. Answer comes from the group with the
    # strongest top source; all qualifying sources are combined.
    best: KmragQueryResult | None = None
    best_score = -1.0
    all_sources: list[dict] = []
    context_found = False
    merged_meta: dict = {"steps": {"retrieval": {"documents_retrieved": 0}}, "groups": []}

    for owner, group_ids in groups.items():
        res = query_kmrag(
            tenant_id=owner, kb_ids=group_ids, query=query, request_id=request_id, user_id=user_id,
            top_k=cfg["RAG_TOP_K"], alpha=cfg["RAG_ALPHA"], model=cfg["KMRAG_QUERY_MODEL"],
        )
        merged_meta["groups"].append({"owner_tenant": owner, "context_found": res.context_found})
        if res.context_found and res.sources:
            context_found = True
            all_sources.extend(res.sources)
            top = max((float(s.get("score") or 0) for s in res.sources), default=0.0)
            if top > best_score:
                best_score, best = top, res

    if not context_found or best is None:
        return KmragQueryResult(answer="", context_found=False, sources=[], metadata=merged_meta, request_id=request_id)
    return KmragQueryResult(
        answer=best.answer, context_found=True, sources=all_sources,
        metadata=merged_meta, request_id=request_id,
    )
