from __future__ import annotations

import os

os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault(
    "MODEL_PRICING_JSON",
    '{"gpt-4o-mini":{"input_per_1m_tokens":0.15,"output_per_1m_tokens":0.60}}',
)

import fakeredis
import pytest

from app import create_app
from app.config import TestConfig
from app.constants import KBStatus, Role, TenantStatus
from app.extensions import db, redis_client
from app.models.knowledge_base import KnowledgeBase
from app.models.tenant import Tenant
from app.models.user import User
from app.utils.uuid_utils import new_uuid


@pytest.fixture()
def app():
    application = create_app(TestConfig)
    # Bind an isolated fake Redis for cache/rate-limit/revocation.
    redis_client.bind(fakeredis.FakeredisStrict() if hasattr(fakeredis, "FakeredisStrict")
                      else fakeredis.FakeStrictRedis(decode_responses=True))
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def kmrag_reachable(monkeypatch):
    """Uploads pre-check KMRAG connectivity before touching the DB. Tests treat
    KMRAG as reachable by default (no real network); tests that exercise the
    down-at-precheck path re-patch this to raise KmragUnavailable."""
    monkeypatch.setattr("app.services.document_service.ensure_kmrag_available", lambda: None)


# ── Data helpers ──────────────────────────────────────────────
@pytest.fixture()
def seed(app):
    tenant_a = Tenant(id=new_uuid(), tenant_name="Tenant A", tenant_code="a", status=TenantStatus.ACTIVE)
    tenant_b = Tenant(id=new_uuid(), tenant_name="Tenant B", tenant_code="b", status=TenantStatus.ACTIVE)
    db.session.add_all([tenant_a, tenant_b])
    db.session.flush()

    superadmin = User(id=new_uuid(), tenant_id=None, name="Root", email="root@x.com",
                      role=Role.SUPER_ADMIN, is_active=True)
    superadmin.set_password("password123")
    admin_a = User(id=new_uuid(), tenant_id=tenant_a.id, name="Admin A", email="admin_a@x.com",
                   role=Role.TENANT_ADMIN, is_active=True)
    admin_a.set_password("password123")
    user_a = User(id=new_uuid(), tenant_id=tenant_a.id, name="User A", email="user_a@x.com",
                  role=Role.CHAT_USER, is_active=True)
    user_a.set_password("password123")
    db.session.add_all([superadmin, admin_a, user_a])
    db.session.flush()

    kb_a = KnowledgeBase(id=new_uuid(), tenant_id=tenant_a.id, kb_name="KB A", status=KBStatus.ACTIVE)
    kb_b = KnowledgeBase(id=new_uuid(), tenant_id=tenant_b.id, kb_name="KB B", status=KBStatus.ACTIVE)
    db.session.add_all([kb_a, kb_b])
    db.session.commit()

    return {
        "tenant_a": tenant_a.id, "tenant_b": tenant_b.id,
        "superadmin": superadmin.id, "admin_a": admin_a.id, "user_a": user_a.id,
        "kb_a": kb_a.id, "kb_b": kb_b.id,
    }


def _login(client, email, password="password123"):
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]["access_token"]


@pytest.fixture()
def auth(client, seed):
    def _headers(email):
        return {"Authorization": f"Bearer {_login(client, email)}"}
    return _headers


@pytest.fixture()
def assign_user_kb(seed):
    """Give the seeded chat user explicit KB access for tests that chat as them."""
    def _assign(user_id=None, kb_id=None, assigned_by=None):
        from app.models.user_kb_assignment import UserKnowledgeBaseAssignment

        user_id = user_id or seed["user_a"]
        kb_id = kb_id or seed["kb_a"]
        assigned_by = assigned_by or seed["admin_a"]

        existing = UserKnowledgeBaseAssignment.query.filter_by(user_id=user_id, kb_id=kb_id).first()
        if existing:
            return existing

        row = UserKnowledgeBaseAssignment(
            id=new_uuid(), user_id=user_id, kb_id=kb_id, assigned_by=assigned_by,
        )
        db.session.add(row)
        db.session.commit()
        return row

    return _assign
