"""Authentication: credential verification and JWT issuance."""
from __future__ import annotations

import logging
from datetime import datetime

from flask import current_app
from flask_jwt_extended import create_access_token, create_refresh_token

from app.constants import AuditAction
from app.extensions import db
from app.models.user import User
from app.services import audit_service
from app.utils.response_utils import ApiError, unauthorized, validation_error

logger = logging.getLogger(__name__)


def _claims(user: User) -> dict:
    return {"role": user.role, "tenant_id": user.tenant_id}


def authenticate(email: str, password: str) -> dict:
    """Validate credentials and return tokens + user dict.

    Uses a single generic message for both unknown-email and bad-password to
    avoid user enumeration.
    """
    generic = "Invalid email or password."
    user = User.query.filter_by(email=(email or "").strip().lower()).first()
    if not user or not user.check_password(password or ""):
        raise ApiError(generic, 401, "invalid_credentials")
    if not user.is_active:
        raise ApiError("This account has been disabled. Please contact your administrator.", 403, "account_disabled")

    user.last_login_at = datetime.utcnow()
    db.session.commit()

    identity = user.id
    access = create_access_token(identity=identity, additional_claims=_claims(user))
    refresh = create_refresh_token(identity=identity, additional_claims=_claims(user))

    audit_service.log_action(
        action=AuditAction.LOGIN, entity_type="user", entity_id=user.id,
        tenant_id=user.tenant_id, user_id=user.id,
    )
    return {"access_token": access, "refresh_token": refresh, "user": user.to_dict()}


def issue_access_token(user: User) -> str:
    return create_access_token(identity=user.id, additional_claims=_claims(user))


def change_password(user: User, current_password: str, new_password: str) -> None:
    """Change the authenticated user's own password after verifying the current
    one. Available to every role (Super User, Tenant Admin, Chat User)."""
    if not user.check_password(current_password or ""):
        raise ApiError("Your current password is incorrect.", 400, "invalid_current_password")
    if (new_password or "") == (current_password or ""):
        raise validation_error("The new password must be different from your current password.")
    user.set_password(new_password)
    audit_service.log_action(
        action=AuditAction.PASSWORD_CHANGED, entity_type="user", entity_id=user.id,
        tenant_id=user.tenant_id, user_id=user.id, commit=False,
    )
    db.session.commit()
