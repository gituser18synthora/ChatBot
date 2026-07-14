"""Flask extension singletons, initialized in the app factory."""
from __future__ import annotations

import redis
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData

# Explicit naming convention keeps Alembic autogenerate deterministic across
# PostgreSQL and SQLite (used in tests).
_naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

db = SQLAlchemy(metadata=MetaData(naming_convention=_naming_convention))
migrate = Migrate()
jwt = JWTManager()


class _RedisProxy:
    """Lazily-bound Redis client so `redis_client` is importable app-wide."""

    def __init__(self) -> None:
        self._client: redis.Redis | None = None

    def init_app(self, app) -> None:
        self._client = redis.Redis(
            host=app.config["REDIS_HOST"],
            port=app.config["REDIS_PORT"],
            password=app.config["REDIS_PASSWORD"],
            db=app.config["REDIS_DB"],
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )

    def bind(self, client: redis.Redis) -> None:
        """Inject a client directly (used by tests with fakeredis)."""
        self._client = client

    def __getattr__(self, item):
        if self._client is None:
            raise RuntimeError("Redis client is not initialized")
        return getattr(self._client, item)


redis_client = _RedisProxy()
