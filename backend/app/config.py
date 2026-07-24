"""Environment-driven configuration.

All secrets and tunables come from environment variables (loaded from `.env`
in development via python-dotenv). Nothing sensitive is hardcoded here.
"""
from __future__ import annotations

import json
import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _build_database_uri() -> str:
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "chatbot")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"


def _parse_model_pricing() -> dict:
    raw = os.getenv("MODEL_PRICING_JSON", "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


class Config:
    # ── Flask core ────────────────────────────────────────────
    SECRET_KEY = os.getenv("SECRET_KEY", "change_me")
    ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = ENV == "development"

    # ── Database ──────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI = _build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": _int("DB_POOL_RECYCLE", 280),
        "pool_size": _int("DB_POOL_SIZE", 10),
        "max_overflow": _int("DB_MAX_OVERFLOW", 20),
    }
    # Boot-time schema handling (see app._prepare_schema_on_boot):
    #   DB_AUTO_UPGRADE   -> create DB + migrations + seed at startup (default on)
    #   DB_REQUIRE_CURRENT-> refuse to boot when the schema is behind head
    # Disable DB_AUTO_UPGRADE under multi-worker prod deploys to avoid race on migrate.
    DB_AUTO_UPGRADE = _bool("DB_AUTO_UPGRADE", True)
    DB_REQUIRE_CURRENT = _bool("DB_REQUIRE_CURRENT", False)

    # ── JWT ───────────────────────────────────────────────────
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(seconds=_int("JWT_ACCESS_TOKEN_EXPIRES", 900))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(seconds=_int("JWT_REFRESH_TOKEN_EXPIRES", 1209600))
    JWT_TOKEN_LOCATION = ["cookies"]
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_DECODE_ALGORITHMS = [JWT_ALGORITHM]
    JWT_ENCODE_ISSUER = os.getenv("JWT_ISSUER", "chatbot-api")
    JWT_DECODE_ISSUER = JWT_ENCODE_ISSUER
    JWT_ENCODE_AUDIENCE = os.getenv("JWT_AUDIENCE", "chatbot-web")
    JWT_DECODE_AUDIENCE = JWT_ENCODE_AUDIENCE
    JWT_COOKIE_SECURE = _bool("AUTH_COOKIE_SECURE", ENV != "development")
    JWT_COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "Lax")
    JWT_COOKIE_DOMAIN = os.getenv("AUTH_COOKIE_DOMAIN") or None
    JWT_COOKIE_CSRF_PROTECT = False
    JWT_ACCESS_COOKIE_NAME = os.getenv("AUTH_ACCESS_COOKIE_NAME", "cb_access")
    JWT_REFRESH_COOKIE_NAME = os.getenv("AUTH_REFRESH_COOKIE_NAME", "cb_refresh")
    JWT_ACCESS_COOKIE_PATH = "/"
    JWT_REFRESH_COOKIE_PATH = "/api/v1/auth/refresh"
    AUTH_CSRF_COOKIE_NAME = os.getenv("AUTH_CSRF_COOKIE_NAME", "cb_csrf")
    AUTH_CSRF_HEADER_NAME = os.getenv("AUTH_CSRF_HEADER_NAME", "X-CSRF-Token")
    AUTH_COOKIE_SECURE = JWT_COOKIE_SECURE
    AUTH_COOKIE_SAMESITE = JWT_COOKIE_SAMESITE
    AUTH_COOKIE_DOMAIN = JWT_COOKIE_DOMAIN
    AUTH_SESSION_DAYS = _int("AUTH_SESSION_DAYS", 14)
    AUTH_MAX_FAILED_LOGINS = _int("AUTH_MAX_FAILED_LOGINS", 5)
    AUTH_LOCK_MINUTES = _int("AUTH_LOCK_MINUTES", 15)
    AUTH_PASSWORD_MIN_LENGTH = _int("AUTH_PASSWORD_MIN_LENGTH", 12)
    AUTH_REFRESH_HASH_SECRET = os.getenv("AUTH_REFRESH_HASH_SECRET", JWT_SECRET_KEY)
    AUTH_DEVICE_ID_BYTES = _int("AUTH_DEVICE_ID_BYTES", 24)
    AUTH_LOGIN_RATE_LIMIT_PER_MINUTE = _int("AUTH_LOGIN_RATE_LIMIT_PER_MINUTE", 10)
    AUTH_REFRESH_RATE_LIMIT_PER_MINUTE = _int("AUTH_REFRESH_RATE_LIMIT_PER_MINUTE", 30)

    # ── Redis ─────────────────────────────────────────────────
    REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
    REDIS_PORT = _int("REDIS_PORT", 6379)
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None
    REDIS_DB = _int("REDIS_DB", 0)
    CACHE_TTL_KB_SECONDS = _int("CACHE_TTL_KB_SECONDS", 300)
    CACHE_TTL_TENANT_SECONDS = _int("CACHE_TTL_TENANT_SECONDS", 300)

    # ── OpenAI ────────────────────────────────────────────────
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    OPENAI_ROUTER_MODEL = os.getenv("OPENAI_ROUTER_MODEL", "gpt-4o-mini")

    # ── KMRAG ─────────────────────────────────────────────────
    KMRAG_BASE_URL = os.getenv("KMRAG_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    KMRAG_UPLOAD_ENDPOINT = os.getenv("KMRAG_UPLOAD_ENDPOINT", "/upload")
    KMRAG_RETRIEVAL_ENDPOINT = os.getenv("KMRAG_RETRIEVAL_ENDPOINT", "/query")
    KMRAG_REQUEST_TIMEOUT_SECONDS = _int("KMRAG_REQUEST_TIMEOUT_SECONDS", 120)
    KMRAG_MAX_RETRY_COUNT = _int("KMRAG_MAX_RETRY_COUNT", 2)
    KMRAG_QUERY_MODEL = os.getenv("KMRAG_QUERY_MODEL", "gpt-4o-mini")
    # Model recorded against document-ingestion usage rows. Ingestion is
    # dominated by embedding calls (OCR/structuring LLM tokens are folded into
    # the same KMRAG-reported total), so we label the row with the embedding
    # model. Must mirror KMRAG's EMBEDDING_MODEL for the per-model cost
    # breakdown to line up. Cost is taken from KMRAG, not priced locally.
    KMRAG_EMBEDDING_MODEL = os.getenv("KMRAG_EMBEDDING_MODEL", "text-embedding-3-small")
    # Ingestion-status + per-file delete endpoint on KMRAG ({kb_id} substituted).
    KMRAG_KB_FILES_ENDPOINT = os.getenv("KMRAG_KB_FILES_ENDPOINT", "/kb/{kb_id}/files")
    # A document still `processing` after this long (with no KMRAG kb_files row)
    # is marked `failed` so it never lingers. Large OCR/PDF jobs take minutes.
    DOCUMENT_PROCESSING_TIMEOUT_MINUTES = _int("DOCUMENT_PROCESSING_TIMEOUT_MINUTES", 30)

    # ── Uploads ───────────────────────────────────────────────
    MAX_UPLOAD_FILE_SIZE_MB = _int("MAX_UPLOAD_FILE_SIZE_MB", 50)
    MAX_CONTENT_LENGTH = MAX_UPLOAD_FILE_SIZE_MB * 1024 * 1024
    ALLOWED_FILE_EXTENSIONS = {
        e.strip().lower()
        for e in os.getenv("ALLOWED_FILE_EXTENSIONS", "pdf,docx,txt,csv,xlsx,jpg,jpeg,png").split(",")
        if e.strip()
    }
    UPLOAD_TMP_DIR = os.getenv("UPLOAD_TMP_DIR", "/tmp/chatbot-uploads")

    # ── Retrieval ─────────────────────────────────────────────
    RAG_TOP_K = _int("RAG_TOP_K", 6)
    RAG_ALPHA = _float("RAG_ALPHA", 0.5)
    # Cosine-similarity gate for the VECTOR leg of KMRAG sources only (a BM25
    # match qualifies on its own). Keep aligned with KMRAG's
    # MIN_RETRIEVAL_SCORE — both judge the same vector_score signal.
    RAG_MIN_RELEVANCE_SCORE = _float("RAG_MIN_RELEVANCE_SCORE", 0.35)

    # ── Chat answer cache ─────────────────────────────────────
    # Exact-repeat answers within the same conversation are served from Redis
    # for this long. 0 disables the cache entirely.
    CHAT_ANSWER_CACHE_TTL_SECONDS = _int("CHAT_ANSWER_CACHE_TTL_SECONDS", 3600)

    # ── Rate limiting ─────────────────────────────────────────
    RATE_LIMIT_CHAT_PER_MINUTE = _int("RATE_LIMIT_CHAT_PER_MINUTE", 30)
    # Generous by default: real bulk document uploads (and repeated testing)
    # should not trip the limiter. Tighten via env if needed.
    RATE_LIMIT_UPLOAD_PER_MINUTE = _int("RATE_LIMIT_UPLOAD_PER_MINUTE", 120)

    # ── Pricing ───────────────────────────────────────────────
    MODEL_PRICING = _parse_model_pricing()

    # ── Logging ───────────────────────────────────────────────
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_JSON = _bool("LOG_JSON", True)


class TestConfig(Config):
    TESTING = True
    ENV = "testing"
    DEBUG = True
    # In-memory SQLite so tests need no external PostgreSQL. Models avoid dialect-only types.
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    AUTH_PASSWORD_MIN_LENGTH = 8
    JWT_COOKIE_SECURE = False
    AUTH_COOKIE_SECURE = False
    JWT_TOKEN_LOCATION = ["headers", "cookies"]


def validate_auth_config(config) -> None:
    def value(name):
        return config.get(name) if hasattr(config, "get") else getattr(config, name)

    env = value("ENV")
    secret = value("JWT_SECRET_KEY")
    if not secret or (env != "testing" and secret in {"change_me", "test-jwt-secret"}):
        raise RuntimeError("JWT_SECRET_KEY must be set to a strong secret.")
    if not value("JWT_ENCODE_ISSUER") or not value("JWT_ENCODE_AUDIENCE"):
        raise RuntimeError("JWT issuer and audience are required.")
    if env != "testing" and value("JWT_ACCESS_TOKEN_EXPIRES") > timedelta(minutes=15):
        raise RuntimeError("JWT access token lifetime must be 15 minutes or less.")
    if value("JWT_ALGORITHM") not in {"HS256", "HS384", "HS512"}:
        raise RuntimeError("JWT_ALGORITHM must be explicitly allowed.")
    if value("JWT_COOKIE_SAMESITE") not in {"Strict", "Lax", "None"}:
        raise RuntimeError("AUTH_COOKIE_SAMESITE must be Strict, Lax, or None.")
    if env == "production" and not value("JWT_COOKIE_SECURE"):
        raise RuntimeError("Secure auth cookies are required in production.")


def get_config() -> type[Config]:
    selected = TestConfig if os.getenv("FLASK_ENV") == "testing" else Config
    validate_auth_config(selected)
    return selected
