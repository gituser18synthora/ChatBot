"""Tests for the database bootstrap helpers (app/db_init.py)."""
from __future__ import annotations

from sqlalchemy.engine import make_url

from app import db_init
from app.constants import Role
from app.models.user import User


def test_without_database_strips_db_name_but_keeps_rest():
    url = make_url("mysql+pymysql://u:p@host:3306/mydb?charset=utf8mb4")
    stripped = db_init._without_database(url)
    assert stripped.database is None
    assert stripped.host == "host"
    assert stripped.username == "u"
    assert stripped.query.get("charset") == "utf8mb4"


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


def test_seed_default_data_skips_without_credentials(app, monkeypatch):
    monkeypatch.delenv("SEED_SUPERADMIN_EMAIL", raising=False)
    monkeypatch.delenv("SEED_SUPERADMIN_PASSWORD", raising=False)

    db_init.seed_default_data(app)  # must not raise

    assert User.query.filter_by(role=Role.SUPER_ADMIN).count() == 0


def test_verify_schema_current_raises_when_behind(app):
    # The create_all() test DB is not Alembic-stamped, so it is "behind head".
    try:
        db_init.verify_schema_current(app)
    except db_init.DatabaseInitError as exc:
        assert "not up to date" in str(exc).lower()
    else:
        raise AssertionError("expected DatabaseInitError for an un-stamped schema")
