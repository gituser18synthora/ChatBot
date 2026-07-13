from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint
from flask_jwt_extended import (
    get_jwt,
    jwt_required,
)

from app.constants import AuditAction
from app.middleware.auth_middleware import current_user, require_auth
from app.schemas import load_body
from app.schemas.auth_schema import LoginSchema
from app.services import audit_service, auth_service
from app.services.redis_service import revoke_token
from app.utils.response_utils import success

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


@bp.post("/login")
def login():
    data = load_body(LoginSchema())
    result = auth_service.authenticate(data["email"], data["password"])
    return success(result)


@bp.post("/logout")
@require_auth
def logout():
    claims = get_jwt()
    user = current_user()
    # Revoke the current access token until its natural expiry.
    exp = claims.get("exp")
    ttl = max(1, int(exp - datetime.now(tz=timezone.utc).timestamp())) if exp else 3600
    revoke_token(claims["jti"], ttl)
    audit_service.log_action(
        action=AuditAction.LOGOUT, entity_type="user", entity_id=user.id,
        tenant_id=user.tenant_id, user_id=user.id,
    )
    return success({"message": "Logged out."})


@bp.get("/me")
@require_auth
def me():
    return success({"user": current_user().to_dict()})


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    user = current_user()
    return success({"access_token": auth_service.issue_access_token(user)})
