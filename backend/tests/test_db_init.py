"""Tests for the database bootstrap helpers (app/db_init.py)."""
from __future__ import annotations

from sqlalchemy.engine import make_url

from app import db_init
from app.config import _build_database_uri
from app.constants import Role
from app.models.user import User


def test_build_database_uri_defaults_to_postgres(monkeypatch):
    for var in ("DATABASE_URL", "POSTGRES_USER", "POSTGRES_PASSWORD",
                "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB"):
        monkeypatch.delenv(var, raising=False)
    uri = _build_database_uri()
    url = make_url(uri)
    assert url.get_backend_name() == "postgresql"
    assert url.drivername == "postgresql+psycopg"
    assert url.port == 5432


def test_build_database_uri_honors_explicit_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/mine")
    assert _build_database_uri() == "postgresql+psycopg://u:p@db:5432/mine"


def test_ensure_database_exists_is_noop_for_sqlite(app):
    # The test app runs on SQLite; database creation must be a safe no-op.
    db_init.ensure_database_exists(app)  # must not raise


def test_schema_status_returns_tuple(app):
    is_current, current, heads = db_init.schema_status(app)
    assert isinstance(current, set) and isinstance(heads, set)
    # On the create_all() test DB there is no alembic_version stamp.
    assert current == set()


def test_seed_default_data_creates_super_admin_once(app, monkeypatch):
    monkeypatch.setenv("SEED_SUPERADMIN_EMAIL", "Root@Example.com")
    monkeypatch.setenv("SEED_SUPERADMIN_PASSWORD", "StrongPass123")
    monkeypatch.setenv("SEED_SUPERADMIN_NAME", "Root")

    db_init.seed_default_data(app)
    db_init.seed_default_data(app)  # second run must not duplicate

    admins = User.query.filter_by(role=Role.SUPER_ADMIN).all()
    assert len(admins) == 1
    assert admins[0].email == "root@example.com"  # normalized to lowercase
    assert admins[0].tenant_id is None


def test_seed_default_data_creates_default_super_admin_without_env(app, monkeypatch):
    # With no SEED_SUPERADMIN_* configured, a fresh DB must still get a usable
    # login: the built-in default Super Admin is created (and creating twice
    # does not duplicate it).
    monkeypatch.delenv("SEED_SUPERADMIN_EMAIL", raising=False)
    monkeypatch.delenv("SEED_SUPERADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("SEED_SUPERADMIN_NAME", raising=False)

    db_init.seed_default_data(app)
    db_init.seed_default_data(app)  # idempotent

    admins = User.query.filter_by(role=Role.SUPER_ADMIN).all()
    assert len(admins) == 1
    assert admins[0].email == db_init.DEFAULT_SUPERADMIN_EMAIL
    assert admins[0].tenant_id is None
    # The default password must actually authenticate.
    assert admins[0].check_password(db_init.DEFAULT_SUPERADMIN_PASSWORD)


def test_verify_schema_current_raises_when_behind(app):
    # The create_all() test DB is not Alembic-stamped, so it is "behind head".
    try:
        db_init.verify_schema_current(app)
    except db_init.DatabaseInitError as exc:
        assert "not up to date" in str(exc).lower()
    else:
        raise AssertionError("expected DatabaseInitError for an un-stamped schema")
