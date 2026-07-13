"""Per-user Knowledge Base assignment.

Assignment applies to CHAT USERS only and controls which KBs their chat is
grounded in:

  - Chat User with no assignments -> all tenant-accessible KBs (automatic).
  - Chat User with one or more    -> restricted to exactly those KBs.
  - Tenant Admins / other roles   -> always all tenant-accessible KBs
                                     (assignment is not available for them).

Every assignable KB must be selectable by the user's tenant (owned by the tenant
or shared to it by the Super Tenant). Super User manages this for any tenant;
a Tenant Admin only for users inside their own tenant.
"""
from __future__ import annotations

from app.constants import AuditAction, KBStatus, Role
from app.extensions import db
from app.models.user import User
from app.models.user_kb_assignment import UserKnowledgeBaseAssignment
from app.services import assignment_service, audit_service, user_service
from app.utils.response_utils import forbidden, not_found, validation_error
from app.utils.uuid_utils import new_uuid


# ── Permission helper ─────────────────────────────────────────
def _load_target(actor: User, user_id: str) -> User:
    """Load a user the actor is allowed to manage KB access for."""
    target = user_service.get_user(user_id)
    if actor.role != Role.SUPER_ADMIN:
        # Tenant Admins may only manage users inside their own tenant.
        if target.tenant_id != actor.tenant_id:
            raise not_found("The requested user was not found.")
    if not target.tenant_id:
        # Super Admins have no tenant and therefore no KB scope.
        raise validation_error("This user is not attached to a tenant and cannot be scoped to knowledge bases.")
    return target


# ── Reads ─────────────────────────────────────────────────────
def _assigned_ids(user_id: str) -> set[str]:
    rows = UserKnowledgeBaseAssignment.query.filter_by(user_id=user_id).all()
    return {r.kb_id for r in rows}


def get_user_kb_access(actor: User, user_id: str) -> dict:
    """Return the assignable KBs for a user with a per-KB `assigned` flag.

    `assigned_kb_ids` is the current explicit selection; an empty selection
    means the user searches all tenant KBs automatically. `available` lists
    every KB the tenant can select, so the UI can render checkboxes even when
    nothing is assigned yet.
    """
    target = _load_target(actor, user_id)
    selectable = assignment_service.selectable_kbs_for_tenant(target.tenant_id)
    owned = {kb.id for kb in selectable if kb.tenant_id == target.tenant_id}
    assigned = _assigned_ids(target.id)
    return {
        "user_id": target.id,
        "assigned_kb_ids": sorted(assigned),
        "uses_all_kbs": not assigned,
        "available": [
            {
                "id": kb.id,
                "kb_name": kb.kb_name,
                "shared": kb.id not in owned,
                "status": kb.status,
                "status_message": kb.status_message,
                "ready": kb.status == KBStatus.READY,
                "assigned": kb.id in assigned,
            }
            for kb in selectable
        ],
    }


# ── Writes ────────────────────────────────────────────────────
def set_user_kbs(actor: User, user_id: str, kb_ids: list[str]) -> dict:
    """Replace a Chat User's KB assignments with `kb_ids` (deduped).

    An empty list clears all assignments, which means the Chat User searches
    all tenant-accessible KBs automatically. Each id must be selectable by the
    tenant. Only Chat Users can be scoped — every other role always uses all
    tenant KBs.
    """
    target = _load_target(actor, user_id)
    if target.role != Role.CHAT_USER:
        raise validation_error(
            "Knowledge Base assignment is only available for Chat Users. "
            "Tenant Admins always use all tenant Knowledge Bases."
        )
    wanted = list(dict.fromkeys(kb_ids or []))

    if wanted:
        selectable_ids = {kb.id for kb in assignment_service.selectable_kbs_for_tenant(target.tenant_id)}
        invalid = [k for k in wanted if k not in selectable_ids]
        if invalid:
            raise forbidden("One or more selected knowledge bases are not available to this user's tenant.")

    existing = {r.kb_id: r for r in UserKnowledgeBaseAssignment.query.filter_by(user_id=target.id).all()}
    wanted_set = set(wanted)

    # Remove assignments no longer wanted.
    for kb_id, row in existing.items():
        if kb_id not in wanted_set:
            db.session.delete(row)
    # Add newly wanted assignments.
    for kb_id in wanted:
        if kb_id not in existing:
            db.session.add(UserKnowledgeBaseAssignment(
                id=new_uuid(), user_id=target.id, kb_id=kb_id, assigned_by=actor.id,
            ))

    action = AuditAction.USER_KB_ASSIGNED if wanted else AuditAction.USER_KB_UNASSIGNED
    audit_service.log_action(
        action=action, entity_type="user", entity_id=target.id,
        tenant_id=target.tenant_id, user_id=actor.id,
        new_data={"kb_ids": wanted}, commit=False,
    )
    db.session.commit()
    return get_user_kb_access(actor, target.id)


# ── Retrieval helpers (used by chat) ──────────────────────────
def effective_kb_ids_for_user(user: User) -> list[str]:
    """The KBs a user's chat should search, in a stable order.

    Chat Users with explicit assignments are restricted to those KBs (still
    accessible + ready); with none, they automatically search every KB
    accessible to their tenant. Tenant Admins and other roles always use every
    tenant-accessible KB. Assignments to KBs that were since deleted,
    deactivated, or unshared are silently dropped.
    """
    if not user.tenant_id:
        return []
    selectable = assignment_service.selectable_kbs_for_tenant(user.tenant_id)
    selectable_ids = [kb.id for kb in selectable if kb.status == KBStatus.READY]
    assigned = _assigned_ids(user.id) if user.role == Role.CHAT_USER else set()
    if assigned:
        return [kb_id for kb_id in selectable_ids if kb_id in assigned]
    return selectable_ids


def selectable_kbs_for_user(user: User) -> list[dict]:
    """The KB choices to show a user when starting a chat: their effective set,
    each flagged `shared` when it is a Super Tenant KB rather than an owned one.

    Includes ingestion visibility so the chat UI can be honest about state:
    `document_count` (non-deleted docs), `indexed_count` (fully ingested), and
    `ready` (retrieval will actually find content in this KB).
    """
    if not user.tenant_id:
        return []
    selectable = assignment_service.selectable_kbs_for_tenant(user.tenant_id)
    for kb in selectable:
        try:
            from app.services import document_service
            document_service.reconcile_kb_documents(kb.id)
        except Exception:
            db.session.rollback()
    selectable = assignment_service.selectable_kbs_for_tenant(user.tenant_id)
    owned = {kb.id for kb in selectable if kb.tenant_id == user.tenant_id}
    # Chat Users list their explicit assignments even if not ready yet (so the
    # UI can be honest about indexing state); with none, everyone falls back to
    # the effective set (all tenant KBs).
    explicit = _assigned_ids(user.id) if user.role == Role.CHAT_USER else set()
    if explicit:
        chosen = [kb for kb in selectable if kb.id in explicit]
    else:
        effective = set(effective_kb_ids_for_user(user))
        chosen = [kb for kb in selectable if kb.id in effective]

    doc_counts, indexed_counts = _document_counts([kb.id for kb in chosen])
    return [
        {
            "id": kb.id,
            "kb_name": kb.kb_name,
            "shared": kb.id not in owned,
            "status": kb.status,
            "status_message": kb.status_message,
            "document_count": doc_counts.get(kb.id, 0),
            "indexed_count": indexed_counts.get(kb.id, 0),
            "ready": kb.status == KBStatus.READY and indexed_counts.get(kb.id, 0) > 0,
        }
        for kb in chosen
    ]


def _document_counts(kb_ids: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    """(non-deleted doc count, indexed doc count) per kb_id."""
    if not kb_ids:
        return {}, {}
    from app.constants import DocumentStatus
    from app.models.document import Document

    rows = (
        db.session.query(Document.kb_id, Document.upload_status, db.func.count(Document.id))
        .filter(Document.kb_id.in_(kb_ids), Document.upload_status != DocumentStatus.DELETED)
        .group_by(Document.kb_id, Document.upload_status)
        .all()
    )
    totals: dict[str, int] = {}
    indexed: dict[str, int] = {}
    for kb_id, status, count in rows:
        totals[kb_id] = totals.get(kb_id, 0) + count
        if status == DocumentStatus.COMPLETED:
            indexed[kb_id] = indexed.get(kb_id, 0) + count
    return totals, indexed


def assert_selectable(user: User, kb_ids: list[str]) -> None:
    """Guard: every kb_id must be within the user's effective (allowed) set."""
    if not kb_ids:
        return
    allowed = set(effective_kb_ids_for_user(user))
    if any(k not in allowed for k in kb_ids):
        raise forbidden("One or more selected knowledge bases are not available to you.")
