"""Chat orchestration: sessions, messages, and the retrieval-first pipeline.

Pipeline for a user message:
  cache lookup -> RAG retrieval (KMRAG) whenever queryable KBs exist
  -> grounded answer, or mode-dependent fallback (rag_first: disclosed general
     answer; rag_only: explicit not-found message)
  -> persist assistant msg + sources + usage/cost -> cache save.

Retrieval always runs BEFORE any general LLM call: whether the Knowledge Bases
can answer a question is a property of their contents, so no up-front intent
classifier can decide it reliably. The KMRAG request_id is the chat session id,
so KMRAG's own answer caches and conversation history work per conversation.

Answer modes: normal | document_rag | no_document_evidence | error.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime
from decimal import Decimal

from flask import current_app

from app.constants import AnswerMode, AuditAction, ChatRole, DocumentStatus, RagMode, RequestType, Role
from app.extensions import db
from app.integrations import openai_client
from app.integrations.kmrag_client import KmragQueryRejected, KmragUnavailable
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession, ChatSessionKnowledgeBase
from app.models.chat_source import ChatSource
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.tenant import Tenant
from app.models.user import User
from app.services import (
    audit_service,
    cost_service,
    retrieval_service,
    user_kb_service,
)
from app.services.redis_service import cache_get_json, cache_set_json
from app.utils import language_utils
from app.utils.response_utils import ApiError, forbidden, not_found
from app.utils.uuid_utils import new_uuid

logger = logging.getLogger(__name__)

# Cap how many prior turns we send to the general model (keeps cost bounded).
_HISTORY_TURNS = 10
_NO_KB_AVAILABLE_MESSAGE = "No Knowledge Base is available for your account yet. Please contact your Tenant Admin."
_KB_NOT_READY_MESSAGE = "Knowledge Base is not ready for chat yet."


def _require_tenant(user: User) -> None:
    """Chat is tenant-scoped. Super Admins have no tenant, so they cannot chat —
    they manage the platform and view conversations from the admin console."""
    if not user.tenant_id:
        raise ApiError(
            "Super Admin accounts are not linked to a tenant and cannot start chats. "
            "Use a Tenant Admin or Chat User account to chat.",
            403,
            "no_tenant_for_chat",
        )


# ── Session management ────────────────────────────────────────
def create_session(user: User, title: str | None, kb_ids: list[str]) -> ChatSession:
    """Create a chat session immediately. Chat Users are never blocked here:
    KB readiness is reported per-message with a clean answer instead, so
    'Start a New Chat' always drops the user straight into the chat UI."""
    _require_tenant(user)
    if user.role == Role.CHAT_USER and kb_ids:
        raise forbidden("Chat Users cannot select knowledge bases. Your Knowledge Bases are applied automatically.")

    # Validate any explicitly-selected KBs: they must belong to the tenant, be
    # ready in KMRAG, and be within the user's allowed set.
    if kb_ids:
        from app.services import document_service
        for kb_id in dict.fromkeys(kb_ids):
            document_service.reconcile_kb_documents(kb_id)
        retrieval_service.validate_kbs_for_tenant(user.tenant_id, kb_ids)
        user_kb_service.assert_selectable(user, kb_ids)

    session = ChatSession(
        id=new_uuid(), tenant_id=user.tenant_id, user_id=user.id,
        title=(title or "New Chat")[:500], status="active",
    )
    db.session.add(session)
    db.session.flush()
    for kb_id in dict.fromkeys(kb_ids or []):
        db.session.add(ChatSessionKnowledgeBase(
            id=new_uuid(), chat_session_id=session.id, tenant_id=user.tenant_id, kb_id=kb_id,
        ))
    audit_service.log_action(
        action=AuditAction.CHAT_SESSION_CREATED, entity_type="chat_session", entity_id=session.id,
        tenant_id=user.tenant_id, user_id=user.id, commit=False,
    )
    db.session.commit()
    return session


def _owned_session(user: User, session_id: str) -> ChatSession:
    session = ChatSession.query.get(session_id)
    if not session or session.deleted_at is not None:
        raise not_found("The requested conversation was not found.")
    # Access rules: Chat Users see only their own; Tenant Admins see any
    # conversation within their own tenant; Super Admins (no tenant) see every
    # tenant's conversations, matching the platform-wide admin list.
    can_view = (
        session.user_id == user.id
        or user.is_super_admin
        or (user.is_tenant_admin and session.tenant_id == user.tenant_id)
    )
    if not can_view:
        raise not_found("The requested conversation was not found.")
    return session


def list_sessions(user: User, page: int, per_page: int, search: str | None = None):
    q = ChatSession.query.filter(
        ChatSession.user_id == user.id, ChatSession.deleted_at.is_(None)
    )
    if search:
        q = q.filter(ChatSession.title.ilike(f"%{search}%"))
    q = q.order_by(ChatSession.updated_at.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return items, total


def list_tenant_sessions(tenant_id: str | None, page: int, per_page: int, search: str | None = None):
    """Admin view: conversations across a tenant (or all tenants for super admin
    when tenant_id is None). Returns enriched dicts with user name + counts."""
    q = ChatSession.query.filter(ChatSession.deleted_at.is_(None))
    if tenant_id is not None:
        q = q.filter(ChatSession.tenant_id == tenant_id)
    if search:
        q = q.filter(ChatSession.title.ilike(f"%{search}%"))
    q = q.order_by(ChatSession.updated_at.desc())
    total = q.count()
    rows = q.offset((page - 1) * per_page).limit(per_page).all()

    user_ids = {s.user_id for s in rows}
    users = {u.id: u.name for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}
    items = []
    for s in rows:
        d = s.to_dict()
        d["user_name"] = users.get(s.user_id)
        d["message_count"] = ChatMessage.query.filter(ChatMessage.chat_session_id == s.id).count()
        items.append(d)
    return items, total


def get_session_with_messages(user: User, session_id: str) -> dict:
    session = _owned_session(user, session_id)
    kb_ids = [l.kb_id for l in session.kb_links]
    messages = (
        ChatMessage.query.filter(ChatMessage.chat_session_id == session.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    kb_name_map = _kb_name_map(kb_ids)
    # KB scope (ids/names) is Knowledge Base metadata — admin-only, like
    # sources. Chat Users see just the conversation itself.
    out = session.to_dict(kb_ids=kb_ids if user.is_admin else [])
    out["kb_names"] = [kb_name_map.get(k) for k in kb_ids] if user.is_admin else []
    out["messages"] = [_message_dict(m, kb_name_map, user) for m in messages]
    return out


def rename_session(user: User, session_id: str, title: str) -> ChatSession:
    session = _owned_session(user, session_id)
    session.title = (title or "").strip()[:500] or session.title
    db.session.commit()
    return session


def delete_session(user: User, session_id: str) -> None:
    session = _owned_session(user, session_id)
    session.deleted_at = datetime.utcnow()
    session.status = "deleted"
    audit_service.log_action(
        action=AuditAction.CHAT_SESSION_DELETED, entity_type="chat_session", entity_id=session.id,
        tenant_id=session.tenant_id, user_id=user.id, commit=False,
    )
    db.session.commit()


# ── Helpers ───────────────────────────────────────────────────
def _kb_name_map(kb_ids: list[str]) -> dict:
    if not kb_ids:
        return {}
    rows = KnowledgeBase.query.filter(KnowledgeBase.id.in_(kb_ids)).all()
    return {kb.id: kb.kb_name for kb in rows}


def _message_dict(m: ChatMessage, kb_name_map: dict, viewer: User) -> dict:
    """Serialize a message for the given viewer.

    Sources reveal Knowledge Base internals (document names, page numbers,
    text previews) — they are visible ONLY to admin roles (Tenant Admin /
    Super Admin). Chat Users get the answer text alone; the `sources` key
    stays present (empty) so the response schema never changes shape.
    Source rows are still persisted for every answer, so admins reviewing a
    Chat User's conversation see its citations."""
    show_sources = viewer.is_admin
    data = m.to_dict(include_sources=show_sources)
    if show_sources:
        for s in data.get("sources", []):
            s["kb_name"] = kb_name_map.get(s.get("kb_id"))
    else:
        data["sources"] = []
    return data


def _recent_history(session_id: str) -> list[dict]:
    rows = (
        ChatMessage.query.filter(ChatMessage.chat_session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(_HISTORY_TURNS * 2)
        .all()
    )
    rows.reverse()
    return [{"role": r.role, "content": r.message_text} for r in rows if r.role in (ChatRole.USER, ChatRole.ASSISTANT)]


def _save_user_message(session: ChatSession, user: User, text: str) -> ChatMessage:
    msg = ChatMessage(
        id=new_uuid(), chat_session_id=session.id, tenant_id=session.tenant_id,
        user_id=user.id, role=ChatRole.USER, message_text=text,
    )
    db.session.add(msg)
    db.session.flush()
    return msg


# ── Automatic chat titles ─────────────────────────────────────
_DEFAULT_TITLES = {"", "new chat"}
_TITLE_MAX_WORDS = 6


def _fallback_title(text: str) -> str:
    """Derive a title from the message itself when the model is unavailable."""
    words = (text or "").strip().split()
    title = " ".join(words[:_TITLE_MAX_WORDS]).rstrip(".,;:!?")
    return (title[:80] or "New Chat")


def _maybe_generate_title(session: ChatSession, user: User, first_message: str) -> None:
    """After the FIRST user message of an untitled chat, set a short generated
    title (like ChatGPT). Best-effort: any failure falls back to a truncated
    form of the message and never fails the chat request. A manual rename
    (custom title) is never overwritten."""
    if (session.title or "").strip().lower() not in _DEFAULT_TITLES:
        return
    user_message_count = ChatMessage.query.filter_by(
        chat_session_id=session.id, role=ChatRole.USER
    ).count()
    if user_message_count != 1:
        return

    title = None
    try:
        completion = openai_client.chat(
            messages=[{
                "role": "user",
                "content": (
                    "Write a short title (at most 6 words, no quotes, no trailing "
                    "punctuation) summarizing this chat message. Reply with the "
                    f"title only.\n\nMessage: {first_message[:500]}"
                ),
            }],
            model=current_app.config["OPENAI_ROUTER_MODEL"],
            temperature=0.2,
            max_tokens=24,
        )
        title = completion.text.strip().strip('"').strip()
        cost_service.record_usage(
            tenant_id=session.tenant_id, model=completion.model,
            input_tokens=completion.prompt_tokens, output_tokens=completion.completion_tokens,
            request_type=RequestType.CHAT_TITLE, user_id=user.id,
            chat_session_id=session.id, commit=False,
        )
    except Exception as exc:
        logger.info("chat title generation failed, using fallback: %s", exc)

    session.title = (title or _fallback_title(first_message))[:500]


# ── Answer cache (exact repeats within a conversation) ────────
def _normalize_query(text: str) -> str:
    """One canonical form so the same question always hashes identically."""
    return " ".join((text or "").strip().lower().split())


def _answer_cache_key(session: ChatSession, user: User, kb_ids: list[str],
                      rag_mode: str, text: str) -> str:
    """Tenant-scoped cache key over everything that can change the answer:
    tenant, user, conversation, KB scope, models, answering mode, and the
    normalized query. Session-scoped on purpose — a cached answer can never
    leak across conversations, users, or tenants."""
    payload = json.dumps({
        "tenant_id": session.tenant_id,
        "user_id": user.id,
        "session_id": session.id,
        "kb_ids": sorted(kb_ids or []),
        "rag_mode": rag_mode,
        "chat_model": current_app.config["OPENAI_CHAT_MODEL"],
        "kmrag_model": current_app.config["KMRAG_QUERY_MODEL"],
        "query": _normalize_query(text),
    }, sort_keys=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"tenant:{session.tenant_id}:chat_answer:{digest}"


def _cached_payload(assistant: ChatMessage, sources: list[dict]) -> dict:
    return {
        "message_text": assistant.message_text,
        "answer_mode": assistant.answer_mode,
        "model_name": assistant.model_name,
        "sources": sources,
    }


def _replay_cached_answer(session: ChatSession, user: User, payload: dict) -> ChatMessage:
    """Materialize a cached answer as a fresh assistant message (zero cost)."""
    assistant = ChatMessage(
        id=new_uuid(), chat_session_id=session.id, tenant_id=session.tenant_id,
        user_id=user.id, role=ChatRole.ASSISTANT,
        message_text=payload["message_text"], answer_mode=payload.get("answer_mode"),
        model_name=payload.get("model_name"),
        prompt_tokens=0, completion_tokens=0, total_tokens=0,
        estimated_cost_usd=Decimal("0"), latency_ms=0,
        retrieval_metadata={"cache_hit": True, "answer_mode": payload.get("answer_mode")},
    )
    db.session.add(assistant)
    db.session.flush()
    for s in payload.get("sources") or []:
        db.session.add(ChatSource(
            id=new_uuid(), message_id=assistant.id, tenant_id=session.tenant_id,
            kb_id=s.get("kb_id"), document_id=s.get("document_id"),
            document_name=s.get("document_name"), page_number=s.get("page_number"),
            relevance_score=(Decimal(str(s["relevance_score"]))
                             if s.get("relevance_score") is not None else None),
            source_text_preview=s.get("source_text_preview"),
        ))
    return assistant


def _persisted_sources(assistant: ChatMessage) -> list[dict]:
    """The source rows of a just-persisted answer, in cacheable form."""
    return [
        {
            "kb_id": s.kb_id, "document_id": s.document_id,
            "document_name": s.document_name, "page_number": s.page_number,
            "relevance_score": (float(s.relevance_score)
                                if s.relevance_score is not None else None),
            "source_text_preview": s.source_text_preview,
        }
        for s in ChatSource.query.filter_by(message_id=assistant.id).all()
    ]


# ── The retrieval-first pipeline ──────────────────────────────
def post_message(user: User, session_id: str, text: str) -> dict:
    _require_tenant(user)
    text = (text or "").strip()
    if not text:
        raise ApiError("Message cannot be empty.", 422, "empty_message")

    session = _owned_session(user, session_id)
    if session.user_id != user.id:
        # Admins can read a tenant conversation but not post into someone else's.
        raise not_found("The requested conversation was not found.")

    # Resolve which KBs to ground this message in. Chat Users never control this:
    # their current admin-managed assignment is the source of truth. Admin users
    # may pin a session to specific KBs, or fall back to their effective set.
    session_kb_ids = [l.kb_id for l in session.kb_links]
    if user.role == Role.CHAT_USER:
        # Chat Users never control KB scope. Their current admin-managed
        # assignment is the only source of truth, even for old sessions that may
        # have stored session KB links from an earlier UI.
        kb_ids = user_kb_service.effective_kb_ids_for_user(user)
    else:
        kb_ids = session_kb_ids or user_kb_service.effective_kb_ids_for_user(user)

    # Tenant answering policy: rag_first (default) may fall back to general AI
    # when the KBs have nothing; rag_only never leaves the Knowledge Bases.
    tenant = Tenant.query.get(session.tenant_id)
    rag_mode = (tenant.rag_mode if tenant and tenant.rag_mode else RagMode.DEFAULT)

    logger.info(
        "CHAT_REQUEST_RECEIVED tenant_id=%s user_id=%s session_id=%s rag_mode=%s kb_scope=%s",
        session.tenant_id, user.id, session.id, rag_mode, sorted(kb_ids or []),
    )

    # 1) Cache lookup — before any retrieval or LLM work.
    cache_ttl = int(current_app.config["CHAT_ANSWER_CACHE_TTL_SECONDS"])
    cache_key = _answer_cache_key(session, user, kb_ids, rag_mode, text)
    cached = cache_get_json(cache_key) if cache_ttl > 0 else None
    logger.info("CACHE_LOOKUP key=%s result=%s", cache_key, "hit" if cached else "miss")

    _save_user_message(session, user, text)

    if cached:
        assistant = _replay_cached_answer(session, user, cached)
        _maybe_generate_title(session, user, text)
        session.updated_at = datetime.utcnow()
        db.session.commit()
        logger.info("CHAT_RESPONSE_COMPLETED session_id=%s source=cache", session.id)
        return {
            "assistant_message": _message_dict(assistant, _kb_name_map(kb_ids), user),
            "session_id": session.id,
            "session_title": session.title,
        }

    # 2) Retrieval first. Only KBs with ingested documents can be queried in
    #    KMRAG (a KB is registered there only once a document is ingested).
    from app.services import document_service
    queryable = document_service.queryable_kb_ids(kb_ids) if kb_ids else []

    assistant = None
    fallback_reason = None

    if queryable:
        assistant, fallback_reason = _try_rag(user, session, queryable, text, rag_mode)
    elif kb_ids:
        fallback_reason = "no_indexed_documents"
        logger.info(
            "RAG_RETRIEVAL_STARTED tenant_id=%s kb_ids=%s skipped=none_queryable",
            session.tenant_id, sorted(kb_ids),
        )
    else:
        fallback_reason = "no_kbs_assigned"

    if assistant is None:
        if user.role == Role.CHAT_USER and fallback_reason in ("no_kbs_assigned", "no_indexed_documents"):
            # Chat Users exist to query the Knowledge Base: when none of their
            # KBs is queryable yet, answer with the clean KB-state message
            # instead of general AI. (no_kbs_assigned = tenant has no READY
            # selectable KB; no_indexed_documents = KBs exist, none indexed.)
            logger.info("LLM_FALLBACK_USED no reason=%s (chat_user)", fallback_reason)
            from app.services import assignment_service
            has_kbs = fallback_reason == "no_indexed_documents" or bool(
                assignment_service.selectable_kbs_for_tenant(user.tenant_id)
            )
            assistant = _no_evidence(
                user, session, kb_ids,
                _KB_NOT_READY_MESSAGE if has_kbs else _NO_KB_AVAILABLE_MESSAGE,
                latency=0,
            )
        elif rag_mode == RagMode.RAG_ONLY:
            logger.info("LLM_FALLBACK_USED no reason=%s (rag_only)", fallback_reason)
            assistant = _no_evidence(user, session, kb_ids, _rag_only_message(fallback_reason), latency=0)
        else:
            logger.info("LLM_FALLBACK_USED yes reason=%s", fallback_reason)
            assistant = _answer_via_general(
                user, session, text,
                searched_without_context=(fallback_reason == "no_rag_context"),
            )
    else:
        logger.info("LLM_FALLBACK_USED no reason=rag_context_found")

    _maybe_generate_title(session, user, text)
    session.updated_at = datetime.utcnow()
    db.session.commit()

    # 3) Cache save. Transient outcomes are never cached — the answer would
    #    wrongly stick for the TTL after recovery. That includes KB-state
    #    answers ("not ready" / "no KB available"): they resolve the moment
    #    indexing finishes, and a cached copy kept replaying "Knowledge Base is
    #    not ready" for up to an hour after the KB became ready.
    transient = fallback_reason in (
        "kmrag_rejected", "kmrag_unavailable", "no_kbs_assigned", "no_indexed_documents",
    )
    if transient:
        logger.info("CACHE_SAVE key=%s status=skipped reason=%s", cache_key, fallback_reason)
    elif cache_ttl > 0:
        try:
            cache_set_json(cache_key, _cached_payload(assistant, _persisted_sources(assistant)), cache_ttl)
            logger.info("CACHE_SAVE key=%s status=success ttl=%ss", cache_key, cache_ttl)
        except Exception as exc:  # pragma: no cover - cache must never break chat
            logger.warning("CACHE_SAVE key=%s status=failed error=%s", cache_key, exc)
    else:
        logger.info("CACHE_SAVE key=%s status=skipped reason=cache_disabled", cache_key)

    source = "rag" if assistant.answer_mode == AnswerMode.DOCUMENT_RAG else (
        "fallback" if assistant.answer_mode == AnswerMode.NORMAL else "no_evidence"
    )
    logger.info("CHAT_RESPONSE_COMPLETED session_id=%s source=%s", session.id, source)

    return {
        "assistant_message": _message_dict(assistant, _kb_name_map(kb_ids), user),
        "session_id": session.id,
        "session_title": session.title,
    }


def _rag_only_message(reason: str | None) -> str:
    if reason == "no_kbs_assigned":
        return _NO_KB_AVAILABLE_MESSAGE
    if reason == "no_indexed_documents":
        return ("None of the available knowledge bases have documents indexed yet. "
                "Upload documents and wait for indexing to finish, then ask again.")
    if reason in ("kmrag_rejected", "kmrag_unavailable"):
        return ("The knowledge base search service is temporarily unavailable. "
                "Please try again shortly.")
    return "I could not find this information in the assigned Knowledge Base(s)."


# Shared response-style rules: mirror the user's language, light emoji use.
_EMOJI_RULE = (
    "You may use at most one or two relevant emojis where they genuinely fit "
    "(a greeting, confirmation, or warning) — never inside quotes, numbers, "
    "IDs, or tables. When unsure, use none."
)


def _reply_style_instruction(text: str) -> str:
    language = language_utils.detect_reply_language(text)
    return (
        " Reply in the same language and style as the user's latest message: "
        f"{language_utils.language_style_instruction(language)}. Do not switch "
        "to or translate into another language unless the user explicitly asks "
        f"for that. {_EMOJI_RULE}"
    )


def _answer_via_general(
    user: User, session: ChatSession, text: str,
    searched_without_context: bool = False,
) -> ChatMessage:
    start = time.time()
    history = _recent_history(session.id)
    if searched_without_context:
        # The KBs were searched first and had nothing relevant. Requirement:
        # the reply must be SHORT, clearly say the information was not found in
        # the Knowledge Base, and never pad with generic overviews (a hard
        # max_tokens cap backs the prompt up).
        system = (
            "You are an assistant grounded in an organization's Knowledge Base. "
            "The Knowledge Base was searched for this question and contains no "
            "relevant information. Reply in one or two short sentences, stating "
            "plainly that the requested information was not found in the "
            "Knowledge Base. Do NOT give generic overviews, examples, category "
            "lists, or background explanations as a substitute. Never invent "
            "organization-specific facts, policies, products, or numbers. Only "
            "if the question is clearly unrelated to the organization (small "
            "talk, arithmetic, a universal fact), answer it briefly instead."
        )
    else:
        system = "You are a helpful assistant. Answer clearly and concisely."
    system += _reply_style_instruction(text)
    messages = [{"role": "system", "content": system}]
    messages.extend(history)
    completion = openai_client.chat(
        messages=messages, model=current_app.config["OPENAI_CHAT_MODEL"], temperature=0.4,
        max_tokens=(120 if searched_without_context else None),
    )
    latency = int((time.time() - start) * 1000)
    costs = cost_service.compute_cost(completion.model, completion.prompt_tokens, completion.completion_tokens)

    assistant = ChatMessage(
        id=new_uuid(), chat_session_id=session.id, tenant_id=session.tenant_id, user_id=user.id,
        role=ChatRole.ASSISTANT, message_text=completion.text, answer_mode=AnswerMode.NORMAL,
        model_name=completion.model, prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens, total_tokens=completion.total_tokens,
        estimated_cost_usd=costs["total_cost_usd"], latency_ms=latency,
        retrieval_metadata={"answer_mode": AnswerMode.NORMAL},
    )
    db.session.add(assistant)
    db.session.flush()
    cost_service.record_usage(
        tenant_id=session.tenant_id, model=completion.model,
        input_tokens=completion.prompt_tokens, output_tokens=completion.completion_tokens,
        request_type=RequestType.CHAT_GENERAL, user_id=user.id,
        chat_session_id=session.id, latency_ms=latency, commit=False,
    )
    return assistant


def _no_evidence(user: User, session: ChatSession, kb_ids: list[str], text: str, latency: int) -> ChatMessage:
    """Build & persist a clean no-document-evidence assistant message (no KMRAG cost)."""
    assistant = ChatMessage(
        id=new_uuid(), chat_session_id=session.id, tenant_id=session.tenant_id, user_id=user.id,
        role=ChatRole.ASSISTANT, message_text=text, answer_mode=AnswerMode.NO_DOCUMENT_EVIDENCE,
        model_name=current_app.config["KMRAG_QUERY_MODEL"],
        prompt_tokens=0, completion_tokens=0, total_tokens=0,
        estimated_cost_usd=Decimal("0"), latency_ms=latency,
        retrieval_metadata={"answer_mode": AnswerMode.NO_DOCUMENT_EVIDENCE, "kb_ids": kb_ids},
    )
    db.session.add(assistant)
    db.session.flush()
    return assistant


def _try_rag(
    user: User, session: ChatSession, queryable_kb_ids: list[str], text: str, rag_mode: str,
) -> tuple[ChatMessage | None, str | None]:
    """Retrieve from KMRAG and, when relevant context exists, persist and return
    the grounded assistant message.

    Returns (assistant, None) on a grounded answer, or (None, reason) when the
    caller must apply the mode-dependent fallback:
      no_rag_context     -> KBs were searched; nothing relevant found
      kmrag_rejected     -> KMRAG refused the query (e.g. docs still indexing)
      kmrag_unavailable  -> KMRAG is down (rag_first only; rag_only re-raises
                            so the client sees a clean 503 and nothing is cached)
    """
    # Re-validate ownership right before the call.
    retrieval_service.validate_kbs_for_tenant(user.tenant_id, queryable_kb_ids)
    start = time.time()

    logger.info(
        "RAG_RETRIEVAL_STARTED tenant_id=%s kb_ids=%s session_id=%s",
        user.tenant_id, sorted(queryable_kb_ids), session.id,
    )
    try:
        # request_id = the chat session id: KMRAG scopes its conversation
        # history AND its exact/semantic answer caches by this id, so it must be
        # stable across the messages of one conversation (a per-HTTP-request id
        # here made KMRAG's cache unable to ever hit).
        result = retrieval_service.retrieve(
            tenant_id=user.tenant_id, kb_ids=queryable_kb_ids, query=text,
            request_id=session.id, user_id=user.id,
        )
    except KmragQueryRejected:
        logger.info("RAG_RETRIEVAL_RESULT total_hits=0 error=kmrag_rejected")
        return None, "kmrag_rejected"
    except KmragUnavailable:
        if rag_mode == RagMode.RAG_ONLY:
            raise  # rag_only has no fallback; surface a clean 503, cache nothing.
        logger.warning("RAG_RETRIEVAL_RESULT total_hits=0 error=kmrag_unavailable")
        return None, "kmrag_unavailable"
    latency = int((time.time() - start) * 1000)

    min_score = float(current_app.config["RAG_MIN_RELEVANCE_SCORE"])
    qualifying = [s for s in result.sources if _qualifies(s, min_score)]

    vector_hits = sum(1 for s in result.sources if s.get("vector_score") is not None)
    bm25_hits = sum(1 for s in result.sources if s.get("bm25_score") is not None)
    logger.info(
        "RAG_RETRIEVAL_RESULT total_hits=%d qualifying=%d vector_hits=%d bm25_hits=%d "
        "context_found=%s latency_ms=%d",
        len(result.sources), len(qualifying), vector_hits, bm25_hits,
        result.context_found, latency,
    )

    if not result.context_found or not qualifying:
        logger.info("RAG_CONTEXT_ATTACHED no context_chars=0")
        return None, "no_rag_context"

    # Prompt assembly happens inside KMRAG (it generates the grounded answer);
    # context_chars here approximates the evidence the answer was built from.
    context_chars = sum(len(s.get("section") or s.get("topic") or "") for s in qualifying)
    logger.info(
        "RAG_CONTEXT_ATTACHED yes sources=%d context_chars=%d", len(qualifying), context_chars
    )

    answer_text = result.answer or "No answer was returned for this question."

    # Reply-language contract: the answer must be in the language/style of the
    # user's latest message. KMRAG's grounded answer may come back in another
    # language (e.g. English for a Hindi query); when the mismatch is visible,
    # re-render it locally without changing its content. Best-effort — on any
    # failure the original grounded answer is kept.
    reply_language = language_utils.detect_reply_language(text)
    language_aligned = False
    align_cost = Decimal("0")
    if result.answer and language_utils.needs_language_alignment(answer_text, reply_language):
        aligned_text, align_cost = _align_answer_language(
            answer_text, text, reply_language, session, user,
        )
        if aligned_text:
            answer_text = aligned_text
            language_aligned = True

    # KMRAG generates the answer; token/cost telemetry may live in its metadata.
    usage = _kmrag_usage(result.metadata)
    assistant = ChatMessage(
        id=new_uuid(), chat_session_id=session.id, tenant_id=session.tenant_id, user_id=user.id,
        role=ChatRole.ASSISTANT, message_text=answer_text, answer_mode=AnswerMode.DOCUMENT_RAG,
        model_name=usage.get("model") or current_app.config["KMRAG_QUERY_MODEL"],
        prompt_tokens=usage.get("input_tokens", 0), completion_tokens=usage.get("output_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
        estimated_cost_usd=Decimal(str(usage.get("total_cost", 0) or 0)) + align_cost,
        latency_ms=latency,
        retrieval_metadata={
            "answer_mode": AnswerMode.DOCUMENT_RAG,
            "context_found": result.context_found,
            "kb_ids": queryable_kb_ids,
            "kmrag_request_id": result.request_id,
            "reply_language": reply_language,
            "language_aligned": language_aligned,
            "documents_retrieved": result.metadata.get("steps", {})
                .get("retrieval", {}).get("documents_retrieved"),
        },
    )
    db.session.add(assistant)
    db.session.flush()

    _persist_sources(assistant, queryable_kb_ids, qualifying)

    # Record KMRAG-reported usage if present; otherwise a zero row (documented:
    # KMRAG-side cost depends on KMRAG telemetry availability).
    if usage.get("total_tokens"):
        cost_service.record_usage(
            tenant_id=session.tenant_id, model=usage.get("model") or current_app.config["KMRAG_QUERY_MODEL"],
            input_tokens=usage.get("input_tokens", 0), output_tokens=usage.get("output_tokens", 0),
            request_type=RequestType.CHAT_RAG, user_id=user.id,
            chat_session_id=session.id, latency_ms=latency, commit=False,
        )
    return assistant, None


def _align_answer_language(
    answer: str, user_text: str, language: str, session: ChatSession, user: User,
) -> tuple[str | None, Decimal]:
    """Re-render a grounded answer in the user's language/style without
    changing its content. Returns (aligned_text, cost) — (None, 0) on failure
    so the caller keeps the original answer."""
    system = (
        "You rewrite an assistant's answer into the user's language and style "
        "without changing its meaning.\n"
        f"- Target: {language_utils.language_style_instruction(language)}.\n"
        "- Preserve EVERY fact, number, date, currency amount, ID, and proper "
        "name exactly as written; translate only the surrounding words.\n"
        "- Do not add, remove, or reorder information. Keep the formatting "
        "(bullets, tables, line breaks). Never translate text inside "
        "quotation marks.\n"
        f"- {_EMOJI_RULE}\n"
        "Reply with the rewritten answer only."
    )
    prompt = (
        f"User's message (language/style reference):\n{user_text}\n\n"
        f"Answer to rewrite:\n{answer}"
    )
    try:
        completion = openai_client.chat(
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": prompt}],
            model=current_app.config["OPENAI_CHAT_MODEL"],
            temperature=0.2,
        )
    except Exception as exc:  # alignment must never break a grounded answer
        logger.warning("ANSWER_LANGUAGE_ALIGNMENT failed target=%s: %s", language, exc)
        return None, Decimal("0")
    if not completion.text:
        return None, Decimal("0")
    costs = cost_service.compute_cost(
        completion.model, completion.prompt_tokens, completion.completion_tokens,
    )
    cost_service.record_usage(
        tenant_id=session.tenant_id, model=completion.model,
        input_tokens=completion.prompt_tokens, output_tokens=completion.completion_tokens,
        request_type=RequestType.CHAT_RAG, user_id=user.id,
        chat_session_id=session.id, commit=False,
    )
    logger.info(
        "ANSWER_LANGUAGE_ALIGNMENT applied target=%s tokens=%d",
        language, completion.total_tokens,
    )
    return completion.text, costs["total_cost_usd"]


def _score(source: dict) -> float | None:
    v = source.get("score")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _float_or_none(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _qualifies(source: dict, min_score: float) -> bool:
    """Judge a KMRAG source on its RAW retrieval signals, mirroring KMRAG's own
    relevance gate.

    The per-source `score` KMRAG returns is a fused RRF rank score
    (~0.005-0.016) or a cross-encoder logit after reranking — never a cosine
    similarity — so comparing it against RAG_MIN_RELEVANCE_SCORE rejects every
    hybrid-search source (that bug silently degraded grounded answers to the
    general-knowledge fallback). A source qualifies when:
      * vector_score (true cosine similarity) >= min_score, OR
      * it has any BM25 lexical match, OR
      * neither raw signal is present — KMRAG already filtered `sources` with
        its own gate, so an unscored source is trusted rather than re-judged
        on the wrong scale.
    """
    vector = _float_or_none(source.get("vector_score"))
    if vector is not None and vector >= min_score:
        return True
    bm25 = _float_or_none(source.get("bm25_score"))
    if bm25 is not None and bm25 > 0:
        return True
    return vector is None and bm25 is None


def _display_relevance(source: dict) -> Decimal | None:
    """A human-meaningful 0..1 relevance for the UI badge.

    After reranking, KMRAG's per-source `score` is a cross-encoder logit (e.g.
    3.14 — which the UI rendered as "314%"); after hybrid fusion it is an RRF
    rank score. Prefer the raw cosine `vector_score`, and fall back to `score`
    only when it is already on a 0..1 scale."""
    for key in ("vector_score", "score"):
        v = _float_or_none(source.get(key))
        if v is not None and 0 < v <= 1:
            return Decimal(str(round(v, 4)))
    return None


def _persist_sources(message: ChatMessage, kb_ids: list[str], sources: list[dict]) -> None:
    # Attribute to the single selected KB when unambiguous; KMRAG source rows do
    # not carry kb_id, so multi-KB sources are stored with kb_id NULL.
    default_kb = kb_ids[0] if len(kb_ids) == 1 else None
    # Best-effort document_id resolution by filename within the tenant.
    for s in sources:
        doc_name = s.get("document_name")
        doc_id = None
        if doc_name and default_kb:
            doc = (
                Document.query.filter_by(
                    kb_id=default_kb,
                    original_filename=doc_name,
                    active_file_key=doc_name,
                    upload_status=DocumentStatus.COMPLETED,
                )
                .order_by(Document.processed_at.desc(), Document.created_at.desc())
                .first()
            )
            doc_id = doc.id if doc else None
        db.session.add(ChatSource(
            id=new_uuid(), message_id=message.id, tenant_id=message.tenant_id,
            kb_id=default_kb, document_id=doc_id, document_name=doc_name,
            page_number=s.get("page_number"),
            relevance_score=_display_relevance(s),
            source_text_preview=s.get("section") or s.get("topic"),
        ))


def _kmrag_usage(metadata: dict) -> dict:
    """Extract token/cost telemetry from KMRAG metadata if present."""
    if not metadata:
        return {}
    return {
        "model": metadata.get("model"),
        "input_tokens": int(metadata.get("input_tokens", 0) or 0),
        "output_tokens": int(metadata.get("output_tokens", 0) or 0),
        "total_tokens": int(metadata.get("total_tokens", 0) or 0),
        "total_cost": metadata.get("total_cost", 0) or 0,
    }
