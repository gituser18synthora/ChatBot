"""Super Tenant KB sharing: assign a shared KB to a (grantee) tenant.

Only KBs owned by the Super Tenant are assignable. Assignments grant a tenant the
right to select and query the KB; ownership (and KMRAG ingestion) stays with the
Super Tenant, and retrieval queries KMRAG using the KB's owner tenant id.
"""
from __future__ import annotations

from app.constants import AuditAction, KBStatus
from app.extensions import db
from app.models.kb_assignment import KnowledgeBaseAssignment
from app.models.knowledge_base import KnowledgeBase
from app.models.tenant import Tenant
from app.services import audit_service, tenant_service
from app.utils.response_utils import ApiError, conflict, not_found
from app.utils.uuid_utils import new_uuid


def assignable_kbs(page: int, per_page: int, search: str | None = None):
    """KBs that can be shared — i.e. owned by the Super Tenant."""
    super_tenant = tenant_service.get_super_tenant()
    if not super_tenant:
        return [], 0, None
    q = KnowledgeBase.query.filter(KnowledgeBase.tenant_id == super_tenant.id)
    if search:
        q = q.filter(KnowledgeBase.kb_name.ilike(f"%{search}%"))
    q = q.order_by(KnowledgeBase.created_at.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return items, total, super_tenant


def _require_super_tenant_kb(kb_id: str) -> tuple[KnowledgeBase, Tenant]:
    super_tenant = tenant_service.get_super_tenant()
    if not super_tenant:
        raise ApiError("No Super Tenant is configured. Designate one before sharing knowledge bases.",
                       409, "no_super_tenant")
    kb = KnowledgeBase.query.get(kb_id)
    if not kb:
        raise not_found("The requested knowledge base was not found.")
    if kb.tenant_id != super_tenant.id:
        raise ApiError("Only Super Tenant knowledge bases can be shared with tenants.", 409, "not_shareable")
    return kb, super_tenant


def list_assignments(kb_id: str) -> list[dict]:
    _require_super_tenant_kb(kb_id)
    rows = KnowledgeBaseAssignment.query.filter_by(kb_id=kb_id).all()
    tenant_ids = [r.tenant_id for r in rows]
    tenants = {t.id: t for t in Tenant.query.filter(Tenant.id.in_(tenant_ids)).all()} if tenant_ids else {}
    out = []
    for r in rows:
        t = tenants.get(r.tenant_id)
        out.append({
            "assignment_id": r.id,
            "tenant_id": r.tenant_id,
            "tenant_name": t.tenant_name if t else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return out


def assign(kb_id: str, tenant_id: str, actor_id: str) -> KnowledgeBaseAssignment:
    kb, super_tenant = _require_super_tenant_kb(kb_id)
    grantee = Tenant.query.get(tenant_id)
    if not grantee:
        raise not_found("The requested tenant was not found.")
    if grantee.id == super_tenant.id:
        raise ApiError("The Super Tenant already owns this knowledge base.", 409, "self_assignment")

    existing = KnowledgeBaseAssignment.query.filter_by(kb_id=kb_id, tenant_id=tenant_id).first()
    if existing:
        raise conflict("This knowledge base is already assigned to that tenant.")

    assignment = KnowledgeBaseAssignment(
        id=new_uuid(), kb_id=kb_id, tenant_id=tenant_id, assigned_by=actor_id,
    )
    db.session.add(assignment)
    audit_service.log_action(
        action=AuditAction.KB_ASSIGNED, entity_type="knowledge_base", entity_id=kb_id,
        tenant_id=tenant_id, user_id=actor_id, new_data={"kb_id": kb_id, "tenant_id": tenant_id}, commit=False,
    )
    db.session.commit()
    return assignment


def unassign(kb_id: str, tenant_id: str, actor_id: str) -> None:
    _require_super_tenant_kb(kb_id)
    assignment = KnowledgeBaseAssignment.query.filter_by(kb_id=kb_id, tenant_id=tenant_id).first()
    if not assignment:
        raise not_found("This assignment was not found.")
    db.session.delete(assignment)
    audit_service.log_action(
        action=AuditAction.KB_UNASSIGNED, entity_type="knowledge_base", entity_id=kb_id,
        tenant_id=tenant_id, user_id=actor_id, old_data={"kb_id": kb_id, "tenant_id": tenant_id}, commit=False,
    )
    db.session.commit()


# ── Access helpers used by retrieval / selection ──────────────
def assigned_kb_ids_for_tenant(tenant_id: str) -> set[str]:
    rows = KnowledgeBaseAssignment.query.filter_by(tenant_id=tenant_id).all()
    return {r.kb_id for r in rows}


def is_kb_accessible(tenant_id: str, kb: KnowledgeBase) -> bool:
    """A tenant may use a KB it owns OR one shared with it."""
    if kb.tenant_id == tenant_id:
        return True
    return KnowledgeBaseAssignment.query.filter_by(kb_id=kb.id, tenant_id=tenant_id).first() is not None


def selectable_kbs_for_tenant(tenant_id: str) -> list[KnowledgeBase]:
    """Assignable KBs the tenant owns + KBs shared with it (deduped).

    Assignment is allowed before readiness so a Tenant Admin can pre-scope a
    Chat User while documents are still indexing. Chat retrieval separately
    filters to `ready` KBs only.
    """
    owned = KnowledgeBase.query.filter(
        KnowledgeBase.tenant_id == tenant_id, KnowledgeBase.status.in_(KBStatus.ASSIGNABLE)
    ).all()
    assigned_ids = assigned_kb_ids_for_tenant(tenant_id)
    assigned = (
        KnowledgeBase.query.filter(
            KnowledgeBase.id.in_(assigned_ids), KnowledgeBase.status.in_(KBStatus.ASSIGNABLE)
        ).all()
        if assigned_ids else []
    )
    by_id = {kb.id: kb for kb in owned}
    for kb in assigned:
        by_id.setdefault(kb.id, kb)
    return sorted(by_id.values(), key=lambda k: (k.kb_name or "").lower())
