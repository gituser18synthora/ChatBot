"""Shared enums and constant values used across the backend."""
from __future__ import annotations


class Role:
    # Stored role identifiers (stable). Display labels differ (see LABELS):
    # super_admin is presented to users as "Super User".
    SUPER_ADMIN = "super_admin"
    TENANT_ADMIN = "tenant_admin"
    CHAT_USER = "chat_user"

    ALL = {SUPER_ADMIN, TENANT_ADMIN, CHAT_USER}
    ADMINS = {SUPER_ADMIN, TENANT_ADMIN}

    LABELS = {
        SUPER_ADMIN: "Super User",
        TENANT_ADMIN: "Tenant Admin",
        CHAT_USER: "Chat User",
    }


class TenantStatus:
    ACTIVE = "active"
    INACTIVE = "inactive"
    ALL = {ACTIVE, INACTIVE}


class RagMode:
    """Per-tenant answering policy.

    RAG_FIRST (default): document-intent questions are answered from the tenant's
    Knowledge Bases; clearly general questions may fall back to general AI.
    RAG_ONLY: every question is answered from the Knowledge Bases only — general
    AI fallback is disabled and unanswerable questions say so explicitly.
    """
    RAG_ONLY = "rag_only"
    RAG_FIRST = "rag_first"
    ALL = {RAG_ONLY, RAG_FIRST}
    DEFAULT = RAG_FIRST


class KBStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    INACTIVE = "inactive"
    # Backwards-compatible alias for older code paths. Public API responses use
    # `ready`, not `active`.
    ACTIVE = READY
    LEGACY_ACTIVE = "active"
    ALL = {PENDING, PROCESSING, READY, FAILED, INACTIVE}
    INPUT_VALUES = ALL | {LEGACY_ACTIVE}
    ASSIGNABLE = {PENDING, PROCESSING, READY, FAILED}


class DocumentStatus:
    PENDING = "pending"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DELETED = "deleted"
    ALL = {PENDING, UPLOADING, PROCESSING, COMPLETED, FAILED, DELETED}
    # Statuses a user may still retry from.
    RETRYABLE = {FAILED, PENDING}


class ChatRole:
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AnswerMode:
    NORMAL = "normal"
    DOCUMENT_RAG = "document_rag"
    MIXED = "mixed"
    NO_DOCUMENT_EVIDENCE = "no_document_evidence"
    ERROR = "error"


class RequestType:
    CHAT_GENERAL = "chat_general"
    CHAT_RAG = "chat_rag"
    QUERY_CLASSIFY = "query_classify"
    CHAT_TITLE = "chat_title"
    # Document ingestion (embedding + OCR + LLM structuring). Billed once per
    # document from KMRAG's reported per-file totals. Ingestion has no
    # prompt/completion split we care about, so these rows carry tokens in
    # total_tokens only — input_tokens/output_tokens stay 0 so that "input
    # tokens" in analytics means query input, never document ingestion.
    DOCUMENT_INGESTION = "document_ingestion"


class AuditAction:
    TENANT_CREATED = "tenant_created"
    TENANT_UPDATED = "tenant_updated"
    TENANT_DEACTIVATED = "tenant_deactivated"
    TENANT_DELETED = "tenant_deleted"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DISABLED = "user_disabled"
    KB_CREATED = "kb_created"
    KB_UPDATED = "kb_updated"
    KB_DELETED = "kb_deleted"
    KB_ASSIGNED = "kb_assigned"
    KB_UNASSIGNED = "kb_unassigned"
    USER_KB_ASSIGNED = "user_kb_assigned"
    USER_KB_UNASSIGNED = "user_kb_unassigned"
    USER_TOKEN_GENERATED = "user_token_generated"
    PROFILE_UPDATED = "profile_updated"
    PASSWORD_CHANGED = "password_changed"
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_RETRY = "document_retry_requested"
    DOCUMENT_DELETED = "document_deleted"
    CHAT_SESSION_CREATED = "chat_session_created"
    CHAT_SESSION_DELETED = "chat_session_deleted"
    LOGIN = "login"
    LOGOUT = "logout"
    VOICE_SETTINGS_UPDATED = "voice_settings_updated"
