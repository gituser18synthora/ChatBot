"""Application factory."""
from __future__ import annotations

import logging

from flask import Flask, g, request
from flask_cors import CORS

from app.config import Config, get_config
from app.extensions import db, jwt, migrate, redis_client
from app.utils.logging_utils import configure_logging, get_request_id, set_request_id


def create_app(config: type[Config] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config or get_config())

    configure_logging(app.config["LOG_LEVEL"], app.config["LOG_JSON"])

    # ── Extensions ────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    if not app.config.get("TESTING"):
        redis_client.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

    _register_jwt_callbacks()
    _register_request_hooks(app)

    from app.api import register_blueprints
    from app.commands import register_commands
    from app.middleware.error_handler import register_error_handlers

    register_blueprints(app)
    register_error_handlers(app)
    register_commands(app)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # Ensure models are imported so metadata is populated.
    from app import models  # noqa: F401

    if not app.config.get("TESTING"):
        _prepare_schema_on_boot(app)

    return app


def _prepare_schema_on_boot(app: Flask) -> None:
    """Confirm the schema is up to date before the app serves traffic.

    Three modes, controlled by config (default = warn, safe for multi-worker
    deploys where each worker must NOT run migrations):
      * DB_AUTO_UPGRADE  -> run `flask db upgrade` automatically at boot, so a
                            fresh environment self-heals. Use for single-instance
                            / dev; avoid with many concurrent workers.
      * DB_REQUIRE_CURRENT -> refuse to boot when the schema is behind (fail
                            fast instead of surfacing confusing runtime 500s).
      * otherwise         -> log a loud warning and boot anyway.
    """
    from app import db_init

    if app.config.get("DB_AUTO_UPGRADE"):
        try:
            db_init.ensure_database_exists(app)
            db_init.run_migrations(app)
        except db_init.DatabaseInitError as exc:
            logging.getLogger(__name__).error("DB_AUTO_UPGRADE failed: %s", exc)
            raise

    try:
        is_current, current, heads = db_init.schema_status(app)
    except Exception as exc:  # pragma: no cover - never block boot on this check
        logging.getLogger(__name__).debug("migration check skipped: %s", exc)
        return

    if is_current:
        return

    message = (
        "DATABASE SCHEMA IS BEHIND: alembic revision %s != head %s. "
        "Run `flask init-db` (or `flask db upgrade`) — missing tables/columns "
        "will cause request failures." % (sorted(current) or "<none>", sorted(heads))
    )
    if app.config.get("DB_REQUIRE_CURRENT"):
        raise db_init.DatabaseInitError(message)
    logging.getLogger(__name__).warning(message)


def _register_request_hooks(app: Flask) -> None:
    @app.before_request
    def _attach_request_id():
        set_request_id(request.headers.get("X-Request-ID"))

    @app.after_request
    def _echo_request_id(response):
        response.headers["X-Request-ID"] = get_request_id()
        return response


def _register_jwt_callbacks() -> None:
    from app.services.redis_service import is_token_revoked

    @jwt.token_in_blocklist_loader
    def _check_revoked(_jwt_header, jwt_payload):
        try:
            return is_token_revoked(jwt_payload["jti"])
        except Exception:
            return False

    @jwt.revoked_token_loader
    def _revoked(_h, _p):
        from app.utils.response_utils import unauthorized
        return unauthorized().to_response()

    @jwt.expired_token_loader
    def _expired(_h, _p):
        from app.utils.response_utils import unauthorized
        return unauthorized("Your session has expired. Please log in again.").to_response()

    @jwt.invalid_token_loader
    def _invalid(_reason):
        from app.utils.response_utils import unauthorized
        return unauthorized("Invalid authentication token.").to_response()

    @jwt.unauthorized_loader
    def _missing(_reason):
        from app.utils.response_utils import unauthorized
        return unauthorized("Authentication is required to access this resource.").to_response()
