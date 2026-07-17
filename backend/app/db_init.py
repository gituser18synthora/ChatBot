"""Database bootstrap: create-if-missing, migrate, verify, and seed.

This is the single source of truth for turning a *fresh* environment (just
`git clone` + a running PostgreSQL server) into a ready-to-serve schema. It is
deliberately **idempotent** — every step is safe to run repeatedly:

    1. ensure_database_exists  -> create the database if it is missing (server-level)
    2. run_migrations          -> `alembic upgrade head` (tables/constraints/idx)
    3. verify_schema_current   -> confirm the DB is at the latest revision
    4. seed_default_data       -> insert required rows only when absent

Schema changes always flow through Alembic migrations (never a bare
`create_all()`), so primary keys, foreign keys, unique constraints and indexes
are created exactly as the versioned migrations define them, existing tables are
never dropped, and the migration history stays authoritative.

Entry points that call this:
    * `flask init-db`            (app/commands.py)
    * `python -m scripts.init_db`
    * app boot, when DB_AUTO_UPGRADE is enabled (app/__init__.py) — default on
"""
from __future__ import annotations

import logging

from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.extensions import db

logger = logging.getLogger(__name__)

# Built-in Super Admin used when SEED_SUPERADMIN_* are not provided, so a freshly
# created database ALWAYS has an account you can log in with. Override via env in
# any real deployment and change the password immediately after first login.
DEFAULT_SUPERADMIN_EMAIL = "admin@chatbot.local"
DEFAULT_SUPERADMIN_PASSWORD = "Admin@123456"
DEFAULT_SUPERADMIN_NAME = "Super Admin"


class DatabaseInitError(RuntimeError):
    """Raised when the database cannot be created, migrated, or verified.

    Carries an operator-facing message; the original cause is chained so the
    full driver traceback is still available in logs.
    """


# ── Step 1: create the database if it does not exist ─────────────────────────
def ensure_database_exists(app: Flask) -> None:
    """Create the target database when it is missing.

    Alembic/`flask db upgrade` connects to an *existing* database — it cannot
    create the database itself. On a brand-new server that database does not
    exist yet, so we connect to the PostgreSQL maintenance database (`postgres`)
    and issue `CREATE DATABASE` when it is missing. Safe to run repeatedly.

    SQLite (used by the test suite) needs nothing here — the file is created on
    first connect. Unsupported backends are surfaced with a clear error rather
    than silently skipped.
    """
    url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
    backend = url.get_backend_name()

    if backend == "sqlite":
        logger.info("DB_INIT step=ensure_database backend=sqlite action=skip (file auto-created)")
        return

    db_name = url.database
    if not db_name:
        raise DatabaseInitError(
            "No database name is configured in SQLALCHEMY_DATABASE_URI. "
            "Set POSTGRES_DB (or DATABASE_URL) before initializing."
        )

    if backend == "postgresql":
        _ensure_postgres_database(url, db_name)
    else:
        logger.warning(
            "DB_INIT step=ensure_database backend=%s action=skip "
            "(automatic database creation is only implemented for PostgreSQL; "
            "create the '%s' database manually if it does not exist)",
            backend, db_name,
        )


def _autocommit_engine(url):
    """An AUTOCOMMIT engine for `url` so `CREATE DATABASE` is not trapped inside
    a transaction. The caller passes a URL pointing at the PostgreSQL
    maintenance database (`postgres`)."""
    return create_engine(url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)


def _ensure_postgres_database(url, db_name: str) -> None:
    # PostgreSQL has no `CREATE DATABASE IF NOT EXISTS`; check first, and connect
    # to the maintenance database to run the DDL.
    logger.info("DB_INIT step=ensure_database backend=postgresql database=%s host=%s", db_name, url.host)
    try:
        engine = _autocommit_engine(url.set(database="postgres"))
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}
            ).first()
            if exists:
                logger.info("DB_INIT step=ensure_database result=already_exists database=%s", db_name)
            else:
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                logger.info("DB_INIT step=ensure_database result=created database=%s", db_name)
        engine.dispose()
    except OperationalError as exc:
        raise DatabaseInitError(_connection_help(url, exc)) from exc
    except SQLAlchemyError as exc:
        raise DatabaseInitError(
            f"Failed to create PostgreSQL database '{db_name}': {exc}."
        ) from exc


def _connection_help(url, exc: Exception) -> str:
    return (
        f"Cannot connect to the database server at {url.host}:{url.port} as "
        f"'{url.username}'. Verify the server is running and the credentials in "
        f"your environment (POSTGRES_HOST/PORT/USER/PASSWORD or DATABASE_URL) are "
        f"correct.\nUnderlying error: {exc}"
    )


# ── Step 2: run migrations (create tables/constraints/indexes) ───────────────
def run_migrations(app: Flask) -> None:
    """Apply all pending Alembic migrations up to head (`flask db upgrade`).

    This creates every table, primary key, foreign key, unique constraint and
    index defined by the versioned migrations. Already-applied migrations are
    skipped by Alembic, so existing tables are never recreated. Requires the
    Flask-Migrate extension to be initialized (done in the app factory).
    """
    from flask_migrate import upgrade

    logger.info("DB_INIT step=migrate action=upgrade target=head")
    try:
        with app.app_context():
            upgrade()
    except OperationalError as exc:
        raise DatabaseInitError(_connection_help(
            make_url(app.config["SQLALCHEMY_DATABASE_URI"]), exc,
        )) from exc
    except Exception as exc:  # alembic surfaces a range of error types
        raise DatabaseInitError(
            f"Database migration failed: {exc}. The schema was left unchanged for "
            "any migration that did not complete; fix the error and re-run."
        ) from exc
    logger.info("DB_INIT step=migrate result=up_to_date")


# ── Step 3: verify the schema is at the latest revision ──────────────────────
def schema_status(app: Flask) -> tuple[bool, set[str], set[str]]:
    """Return (is_current, current_revisions, head_revisions).

    Compares the revision(s) stamped in the database's `alembic_version` table
    against the migration script heads on disk.
    """
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory

    script = ScriptDirectory(str(app.extensions["migrate"].directory))
    heads = set(script.get_heads())
    with app.app_context(), db.engine.connect() as conn:
        current = set(MigrationContext.configure(conn).get_current_heads())
    return current == heads, current, heads


def verify_schema_current(app: Flask) -> None:
    """Raise DatabaseInitError unless the database is at the latest revision."""
    is_current, current, heads = schema_status(app)
    if not is_current:
        raise DatabaseInitError(
            f"Database schema is NOT up to date: at revision "
            f"{sorted(current) or ['<none>']}, expected {sorted(heads)}. "
            "Run `flask init-db` (or `flask db upgrade`) before starting the app."
        )
    logger.info("DB_INIT step=verify result=current revision=%s", sorted(heads))


# ── Step 4: seed required default data (idempotent) ──────────────────────────
def seed_default_data(app: Flask, *, sample_tenant: bool = False) -> None:
    """Insert required default rows that are absent — never duplicates.

    The one *required* default is the first Super Admin. It is created from
    SEED_SUPERADMIN_EMAIL / SEED_SUPERADMIN_PASSWORD when those are set, and
    otherwise from the built-in DEFAULT_SUPERADMIN_* values so a fresh database
    always has an account you can log in with. Seeding from defaults logs a loud
    warning to change the password immediately. Idempotent: an existing account
    with the same email is left untouched.
    """
    import os

    from app.constants import Role
    from app.models.user import User
    from app.utils.uuid_utils import new_uuid

    with app.app_context():
        email = (os.getenv("SEED_SUPERADMIN_EMAIL") or "").strip().lower()
        password = os.getenv("SEED_SUPERADMIN_PASSWORD") or ""
        name = os.getenv("SEED_SUPERADMIN_NAME") or DEFAULT_SUPERADMIN_NAME

        # Fall back to built-in defaults so a fresh DB is never left without a
        # usable login (the whole reason the app couldn't be signed into before).
        using_defaults = not email or not password
        if using_defaults:
            email = email or DEFAULT_SUPERADMIN_EMAIL
            password = password or DEFAULT_SUPERADMIN_PASSWORD

        if User.query.filter_by(email=email).first():
            logger.info("DB_INIT step=seed result=super_admin_exists email=%s", email)
        else:
            user = User(id=new_uuid(), tenant_id=None, name=name, email=email,
                        role=Role.SUPER_ADMIN, is_active=True)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            if using_defaults:
                logger.warning(
                    "DB_INIT step=seed result=super_admin_created_with_DEFAULTS email=%s "
                    "-- CHANGE THIS PASSWORD IMMEDIATELY, or set SEED_SUPERADMIN_EMAIL "
                    "and SEED_SUPERADMIN_PASSWORD before first setup.", email,
                )
            else:
                logger.info("DB_INIT step=seed result=super_admin_created email=%s", email)

        if sample_tenant:
            _seed_sample_tenant()


def _seed_sample_tenant() -> None:
    """Optional local-dev fixtures: a sample tenant + KB (+ admin if a password
    is provided). Kept out of the required seed path — never created in prod."""
    import os

    from app.constants import KBStatus, Role, TenantStatus
    from app.models.knowledge_base import KnowledgeBase
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.utils.uuid_utils import new_uuid

    tenant = Tenant.query.filter_by(tenant_code="sample").first()
    if not tenant:
        tenant = Tenant(id=new_uuid(), tenant_name="Sample Tenant", tenant_code="sample",
                        status=TenantStatus.ACTIVE, contact_name="Ops",
                        contact_email="ops@example.com")
        db.session.add(tenant)
        db.session.flush()
        logger.info("DB_INIT step=seed result=sample_tenant_created id=%s", tenant.id)

    if not KnowledgeBase.query.filter_by(tenant_id=tenant.id).first():
        kb = KnowledgeBase(id=new_uuid(), tenant_id=tenant.id, kb_name="Product Manuals",
                           description="Sample knowledge base", status=KBStatus.PENDING,
                           status_message="Upload documents to start indexing this Knowledge Base.")
        db.session.add(kb)
        logger.info("DB_INIT step=seed result=sample_kb_created id=%s", kb.id)

    admin_pw = os.getenv("SEED_TENANT_ADMIN_PASSWORD")
    if admin_pw and not User.query.filter_by(email="admin@sample.example").first():
        admin = User(id=new_uuid(), tenant_id=tenant.id, name="Sample Admin",
                     email="admin@sample.example", role=Role.TENANT_ADMIN, is_active=True)
        admin.set_password(admin_pw)
        db.session.add(admin)
        logger.info("DB_INIT step=seed result=sample_tenant_admin_created email=admin@sample.example")

    db.session.commit()


# ── Orchestration ────────────────────────────────────────────────────────────
def initialize_database(app: Flask, *, seed: bool = True, sample_tenant: bool = False) -> None:
    """Run the full bootstrap end-to-end. Idempotent and safe to re-run.

    create-if-missing -> migrate -> verify -> seed. Any failure raises
    DatabaseInitError with an operator-facing message (the driver cause is
    chained for the logs).
    """
    logger.info("DB_INIT started uri=%s", _safe_uri(app))
    ensure_database_exists(app)
    run_migrations(app)
    verify_schema_current(app)
    if seed:
        seed_default_data(app, sample_tenant=sample_tenant)
    logger.info("DB_INIT completed successfully")


def _safe_uri(app: Flask) -> str:
    """The configured URI with the password redacted, for logs."""
    try:
        return make_url(app.config["SQLALCHEMY_DATABASE_URI"]).render_as_string(hide_password=True)
    except Exception:  # pragma: no cover - logging must never fail
        return "<unparseable>"
