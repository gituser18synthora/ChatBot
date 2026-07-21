"""Chat User access tokens issued by Tenant Admins / Super Users.

POST /api/v1/users/<user_id>/token generates (or regenerates) a short opaque
token scoped to that Chat User's tenant_id + KB assignments and persists it in
`user_token`. Lookup is by the stored token string — these are not JWTs.
"""
from __future__ import annotations

import secrets

from app.constants import AuditAction, Role
from app.extensions import db
from app.models.user import User
from app.models.user_token import UserToken
from app.services import audit_service, user_kb_service, user_service
from app.utils.response_utils import forbidden, not_found, validation_error
from app.utils.uuid_utils import new_uuid

# 16 random bytes -> 32 hex characters. Regenerating replaces the previous row
# (one active token per Chat User).
_TOKEN_BYTES = 16


def _new_opaque_token() -> str:
    return secrets.token_hex(_TOKEN_BYTES)


def _load_chat_user(actor: User, user_id: str) -> User:
    """Load a Chat User the actor is allowed to issue a token for."""
    target = user_service.get_user(user_id)
    if actor.role != Role.SUPER_ADMIN:
        if target.tenant_id != actor.tenant_id:
            raise not_found("The requested user was not found.")
    if target.role != Role.CHAT_USER:
        raise validation_error("Access tokens can only be generated for Chat Users.")
    if not target.tenant_id:
        raise validation_error("This user is not attached to a tenant.")
    if not target.is_active:
        raise forbidden("Cannot generate a token for a disabled user.")
    return target


def _kb_ids_for_token(user: User) -> list[str]:
    """KB scope snapshot stored on the token.

    Prefer the Chat User's explicit assignments; when none are set they search
    all tenant-accessible KBs, so we snapshot that effective set instead.
    """
    from app.models.user_kb_assignment import UserKnowledgeBaseAssignment

    assigned = [
        r.kb_id
        for r in UserKnowledgeBaseAssignment.query.filter_by(user_id=user.id).all()
    ]
    if assigned:
        return sorted(set(assigned))
    return list(user_kb_service.effective_kb_ids_for_user(user))


def generate_token(actor: User, user_id: str) -> dict:
    """Create or replace the access token for a Chat User."""
    target = _load_chat_user(actor, user_id)
    kb_ids = _kb_ids_for_token(target)
    token = _new_opaque_token()

    row = UserToken.query.filter_by(user_id=target.id).first()
    if row is None:
        row = UserToken(
            id=new_uuid(),
            user_id=target.id,
            tenant_id=target.tenant_id,
            kb_ids=kb_ids,
            token=token,
            created_by=actor.id,
        )
        db.session.add(row)
    else:
        row.tenant_id = target.tenant_id
        row.kb_ids = kb_ids
        row.token = token
        row.created_by = actor.id

    audit_service.log_action(
        action=AuditAction.USER_TOKEN_GENERATED,
        entity_type="user",
        entity_id=target.id,
        tenant_id=target.tenant_id,
        user_id=actor.id,
        new_data={"user_id": target.id, "tenant_id": target.tenant_id, "kb_ids": kb_ids},
        commit=False,
    )
    db.session.commit()
    return row.to_dict()


def get_token(actor: User, user_id: str) -> dict:
    """Return the stored token for a Chat User, if one exists."""
    target = _load_chat_user(actor, user_id)
    row = UserToken.query.filter_by(user_id=target.id).first()
    if row is None:
        raise not_found("No access token has been generated for this user yet.")
    return row.to_dict()
