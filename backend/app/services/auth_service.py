"""Authentication services: sessions, JWT cookies, refresh rotation, and replay detection."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app, request
from flask_jwt_extended import create_access_token, create_refresh_token, decode_token, get_jwt

from app.constants import AuditAction
from app.extensions import db
from app.models.auth_session import AuthSession, RefreshToken
from app.models.user import User
from app.services import audit_service
from app.services.redis_service import check_rate_limit, revoke_token
from app.utils.response_utils import ApiError, unauthorized, validation_error
from app.utils.uuid_utils import new_uuid


def _claims(user: User, session_id: str | None = None, family_id: str | None = None, csrf_token: str | None = None) -> dict:
    claims = {"role": user.role, "tenant_id": user.tenant_id}
    if session_id:
        claims["sid"] = session_id
    if family_id:
        claims["tfam"] = family_id
    if csrf_token:
        claims["csrf"] = csrf_token
    return claims


def _client_ip() -> str | None:
    forwarded = request.headers.get("X-Forwarded-For", "") if request else ""
    return (forwarded.split(",")[0].strip() or request.remote_addr) if request else None


def _hash_value(value: str) -> str:
    secret = current_app.config["AUTH_REFRESH_HASH_SECRET"].encode("utf-8")
    return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()


def _rate_identity(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:32]


def _check_public_rate_limit(bucket: str, identity: str, config_key: str) -> None:
    allowed = check_rate_limit(
        tenant_id="public",
        user_id=_rate_identity(identity or _client_ip() or "unknown"),
        bucket=bucket,
        limit=int(current_app.config.get(config_key, 10)),
        window=60,
    )
    if not allowed:
        raise ApiError("Too many authentication attempts. Please try again shortly.", 429, "rate_limited")


def validate_password_strength(password: str) -> None:
    minimum = int(current_app.config.get("AUTH_PASSWORD_MIN_LENGTH", 12))
    value = password or ""
    if len(value) < minimum:
        raise validation_error(f"Password must be at least {minimum} characters long.")
    checks = [any(c.islower() for c in value), any(c.isupper() for c in value), any(c.isdigit() for c in value), any(not c.isalnum() for c in value)]
    if current_app.config.get("ENV") == "testing":
        return
    if sum(checks) < 3:
        raise validation_error("Password must include at least three of: uppercase, lowercase, number, symbol.")


def _record_failed_login(user: User | None, email: str) -> None:
    audit_service.log_action(
        action=AuditAction.LOGIN_FAILED,
        entity_type="user",
        entity_id=user.id if user else None,
        tenant_id=user.tenant_id if user else None,
        user_id=user.id if user else None,
        new_data={"email": email},
        commit=False,
    )
    if user:
        user.failed_login_count = (user.failed_login_count or 0) + 1
        max_failures = int(current_app.config.get("AUTH_MAX_FAILED_LOGINS", 5))
        if user.failed_login_count >= max_failures:
            user.locked_until = datetime.utcnow() + timedelta(minutes=int(current_app.config.get("AUTH_LOCK_MINUTES", 15)))
            audit_service.log_action(
                action=AuditAction.ACCOUNT_LOCKED,
                entity_type="user",
                entity_id=user.id,
                tenant_id=user.tenant_id,
                user_id=user.id,
                new_data={"locked_until": user.locked_until.isoformat()},
                commit=False,
            )
    db.session.commit()


def _issue_token_pair(user: User, session: AuthSession, family_id: str, parent_jti_hash: str | None = None) -> tuple[str, str, str]:
    csrf = secrets.token_urlsafe(32)
    access = create_access_token(identity=user.id, additional_claims=_claims(user, session.id, csrf_token=csrf))
    refresh = create_refresh_token(identity=user.id, additional_claims=_claims(user, session.id, family_id))
    refresh_claims = decode_token(refresh)
    row = RefreshToken(
        session_id=session.id,
        user_id=user.id,
        family_id=family_id,
        token_hash=_hash_value(refresh),
        jti_hash=_hash_value(refresh_claims["jti"]),
        parent_jti_hash=parent_jti_hash,
        expires_at=datetime.utcfromtimestamp(refresh_claims["exp"]),
    )
    db.session.add(row)
    return access, refresh, csrf


def authenticate(email: str, password: str) -> dict:
    generic = "Invalid email or password."
    normalized = (email or "").strip().lower()
    _check_public_rate_limit("login", normalized, "AUTH_LOGIN_RATE_LIMIT_PER_MINUTE")

    user = User.query.filter_by(email=normalized).first()
    if not user or not user.check_password(password or ""):
        _record_failed_login(user, normalized)
        raise ApiError(generic, 401, "invalid_credentials")
    if user.deleted_at is not None or not user.is_active:
        raise ApiError("This account has been disabled. Please contact your administrator.", 403, "account_disabled")
    if user.is_locked:
        raise ApiError("This account is temporarily locked. Please try again later.", 423, "account_locked")

    now = datetime.utcnow()
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    session = AuthSession(
        user_id=user.id,
        device_id=secrets.token_urlsafe(int(current_app.config.get("AUTH_DEVICE_ID_BYTES", 24))),
        user_agent=(request.headers.get("User-Agent") or "")[:400],
        ip_address=_client_ip(),
        last_used_at=now,
        expires_at=now + timedelta(days=int(current_app.config.get("AUTH_SESSION_DAYS", 14))),
    )
    db.session.add(session)
    db.session.flush()
    family_id = new_uuid()
    access, refresh, csrf = _issue_token_pair(user, session, family_id)
    audit_service.log_action(
        action=AuditAction.LOGIN,
        entity_type="user",
        entity_id=user.id,
        tenant_id=user.tenant_id,
        user_id=user.id,
        new_data={"session_id": session.id, "device_id": session.device_id},
        commit=False,
    )
    db.session.commit()
    return {"access_token": access, "refresh_token": refresh, "csrf_token": csrf, "user": user.to_dict(), "session_id": session.id}


def get_active_session(session_id: str | None, user_id: str | None = None) -> AuthSession:
    session = AuthSession.query.get(session_id) if session_id else None
    if not session or not session.is_active:
        raise unauthorized("Your session is no longer active. Please log in again.")
    if user_id and session.user_id != user_id:
        raise unauthorized("Invalid authentication session.")
    session.last_used_at = datetime.utcnow()
    return session


def issue_access_token(user: User, session_id: str | None = None) -> str:
    if session_id:
        get_active_session(session_id, user.id)
    return create_access_token(identity=user.id, additional_claims=_claims(user, session_id))


def _revoke_refresh_family(family_id: str, reason: str) -> None:
    now = datetime.utcnow()
    RefreshToken.query.filter_by(family_id=family_id, revoked_at=None).update(
        {"revoked_at": now, "revoked_reason": reason}, synchronize_session=False
    )


def _revoke_session(session: AuthSession, reason: str) -> None:
    now = datetime.utcnow()
    session.revoked_at = session.revoked_at or now
    session.revoked_reason = reason
    RefreshToken.query.filter_by(session_id=session.id, revoked_at=None).update(
        {"revoked_at": now, "revoked_reason": reason}, synchronize_session=False
    )


def rotate_refresh_token(encoded_refresh: str) -> dict:
    _check_public_rate_limit("refresh", _client_ip() or "unknown", "AUTH_REFRESH_RATE_LIMIT_PER_MINUTE")
    if not encoded_refresh:
        raise unauthorized("Refresh authentication is required.")
    claims = decode_token(encoded_refresh)
    if claims.get("type") != "refresh":
        raise unauthorized("Invalid refresh token.")

    row = RefreshToken.query.filter_by(token_hash=_hash_value(encoded_refresh)).first()
    session = AuthSession.query.get(claims.get("sid"))
    user = User.query.get(claims.get("sub"))
    if not row:
        if claims.get("tfam"):
            _revoke_refresh_family(claims["tfam"], "unknown_refresh_reuse")
        if session:
            _revoke_session(session, "unknown_refresh_reuse")
        audit_service.log_action(action=AuditAction.REFRESH_REUSE_DETECTED, entity_type="auth_session", entity_id=session.id if session else None, user_id=user.id if user else None, tenant_id=user.tenant_id if user else None, commit=False)
        db.session.commit()
        raise unauthorized("Refresh token reuse detected. Please log in again.")
    if not row.is_active:
        _revoke_refresh_family(row.family_id, "refresh_reuse")
        if session:
            _revoke_session(session, "refresh_reuse")
        audit_service.log_action(action=AuditAction.REFRESH_REUSE_DETECTED, entity_type="auth_session", entity_id=row.session_id, user_id=row.user_id, tenant_id=user.tenant_id if user else None, commit=False)
        db.session.commit()
        raise unauthorized("Refresh token reuse detected. Please log in again.")
    if not session or not session.is_active or not user or not user.is_active or user.deleted_at is not None:
        row.revoked_at = datetime.utcnow()
        row.revoked_reason = "invalid_session"
        db.session.commit()
        raise unauthorized("Your session is no longer active. Please log in again.")

    row.used_at = datetime.utcnow()
    parent_jti_hash = row.jti_hash
    access, refresh, csrf = _issue_token_pair(user, session, row.family_id, parent_jti_hash)
    audit_service.log_action(action=AuditAction.REFRESH_ROTATED, entity_type="auth_session", entity_id=session.id, tenant_id=user.tenant_id, user_id=user.id, commit=False)
    db.session.commit()
    return {"access_token": access, "refresh_token": refresh, "csrf_token": csrf, "user": user.to_dict(), "session_id": session.id}


def logout_current(user: User, claims: dict) -> None:
    session = get_active_session(claims.get("sid"), user.id)
    _revoke_session(session, "logout")
    exp = claims.get("exp")
    ttl = max(1, int(exp - datetime.now(tz=timezone.utc).timestamp())) if exp else 900
    if claims.get("jti"):
        revoke_token(claims["jti"], ttl)
    audit_service.log_action(action=AuditAction.LOGOUT, entity_type="auth_session", entity_id=session.id, tenant_id=user.tenant_id, user_id=user.id, commit=False)
    db.session.commit()


def logout_all(user: User) -> None:
    now = datetime.utcnow()
    AuthSession.query.filter_by(user_id=user.id, revoked_at=None).update({"revoked_at": now, "revoked_reason": "logout_all"}, synchronize_session=False)
    RefreshToken.query.filter_by(user_id=user.id, revoked_at=None).update({"revoked_at": now, "revoked_reason": "logout_all"}, synchronize_session=False)
    audit_service.log_action(action=AuditAction.LOGOUT_ALL, entity_type="user", entity_id=user.id, tenant_id=user.tenant_id, user_id=user.id, commit=False)
    db.session.commit()


def change_password(user: User, current_password: str, new_password: str) -> None:
    if not user.check_password(current_password or ""):
        raise ApiError("Your current password is incorrect.", 400, "invalid_current_password")
    if (new_password or "") == (current_password or ""):
        raise validation_error("The new password must be different from your current password.")
    validate_password_strength(new_password or "")
    user.set_password(new_password)
    logout_all(user)
    audit_service.log_action(
        action=AuditAction.PASSWORD_CHANGED,
        entity_type="user",
        entity_id=user.id,
        tenant_id=user.tenant_id,
        user_id=user.id,
        commit=False,
    )
    db.session.commit()
