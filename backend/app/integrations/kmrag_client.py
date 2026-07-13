"""KMRAG HTTP client — the ONLY place that talks to the KMRAG engine.

Contract (verified against Synthora-AI-dev/kmrag/api/fast.py):

  Upload   POST /upload?tenant_id=&kb_id=&kb_name=   multipart field `file`
           -> 200 {status:"queued", kb_id, file_name, message, kafka_metadata}
           -> 409 kb_id owned by another tenant
           Upload is ASYNC (Kafka). No document id, no completion, no polling.

  Query    POST /query  JSON {query, request_id, tenant_id, user_id?,
                              kb_id?|kb_ids?[], top_k, alpha, model}
           -> {answer, request_id, metadata, upgrade_summary}
           KMRAG generates the answer itself; metadata.context_found flags
           the no-evidence case; metadata.steps.retrieval.sources[] carries
           document_name/page_number/section/topic/score.

Everything here returns clean, frontend-safe results. Raw KMRAG errors, URLs,
and traces are logged internally only, never surfaced.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from flask import current_app

logger = logging.getLogger(__name__)


class KmragUnavailable(Exception):
    """KMRAG could not be reached / timed out / returned 5xx after retries."""


class KmragConflict(Exception):
    """KMRAG rejected the request as a conflict (e.g. kb_id owned elsewhere)."""


class KmragQueryRejected(Exception):
    """KMRAG rejected a /query with a 4xx (not a transient outage).

    Because the chatbot already validated tenant + KB ownership before calling,
    a 4xx here means KMRAG cannot serve the request for these KBs — typically the
    KB has no ingested content in KMRAG yet (KMRAG only knows a KB once a document
    has been ingested under it). Callers treat this as "no queryable content".
    """


@dataclass
class KmragUploadResult:
    ok: bool
    status: str = ""            # e.g. "queued"
    kb_id: str = ""
    file_name: str = ""
    message: str = ""
    request_id: str = ""
    document_id: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class KmragQueryResult:
    answer: str
    context_found: bool
    sources: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    request_id: str = ""


def _cfg(key: str):
    return current_app.config[key]


def _retries() -> int:
    return int(_cfg("KMRAG_MAX_RETRY_COUNT"))


def _timeout() -> int:
    return int(_cfg("KMRAG_REQUEST_TIMEOUT_SECONDS"))


def ensure_kmrag_available() -> None:
    """Fail fast when the KMRAG server is unreachable.

    Called BEFORE an upload creates any KB/document rows, so a down KMRAG
    surfaces only the service error — no failed document rows, no orphan KBs
    left behind by the attempt. Any HTTP response (even 404/503) proves the
    server is up; deeper problems still surface from the real call.
    """
    base = _cfg("KMRAG_BASE_URL")
    try:
        with httpx.Client(timeout=min(_timeout(), 5)) as client:
            client.get(f"{base}/health")
    except httpx.HTTPError as exc:
        logger.warning("KMRAG availability pre-check failed: %s", exc)
        raise KmragUnavailable(
            "KMRAG service is not running. Please start KMRAG and retry document upload."
        ) from exc


def upload_document_to_kmrag(
    *,
    tenant_id: str,
    kb_id: str,
    kb_name: str,
    file_path: str,
    original_filename: str,
    content_type: str,
    request_id: str,
) -> KmragUploadResult:
    """Upload a validated file to KMRAG. Retries with exponential backoff on
    transient transport errors. Raises KmragConflict on 409, KmragUnavailable
    on exhausted retries."""
    base = _cfg("KMRAG_BASE_URL")
    endpoint = _cfg("KMRAG_UPLOAD_ENDPOINT")
    url = f"{base}{endpoint}"
    params = {"tenant_id": tenant_id, "kb_id": kb_id, "kb_name": kb_name}

    last_exc: Exception | None = None
    for attempt in range(_retries() + 1):
        try:
            with open(file_path, "rb") as fh:
                files = {"file": (original_filename, fh, content_type)}
                with httpx.Client(timeout=_timeout()) as client:
                    resp = client.post(
                        url,
                        params=params,
                        files=files,
                        headers={"X-Request-ID": request_id},
                    )
            if resp.status_code == 409:
                logger.warning("KMRAG upload conflict kb_id=%s request_id=%s", kb_id, request_id)
                raise KmragConflict("This knowledge base ID already exists. Please use a different Knowledge Base ID.")
            if resp.status_code >= 500:
                raise httpx.HTTPStatusError("kmrag 5xx", request=resp.request, response=resp)
            if resp.status_code >= 400:
                # 4xx (bad params) — not retryable; log detail internally only.
                logger.error("KMRAG upload rejected %s request_id=%s body=%s",
                             resp.status_code, request_id, resp.text[:500])
                raise KmragUnavailable("Document upload failed during processing. Please retry.")

            data = resp.json()
            return KmragUploadResult(
                ok=True,
                status=data.get("status", ""),
                kb_id=data.get("kb_id", kb_id),
                file_name=data.get("file_name", original_filename),
                message=data.get("message", ""),
                request_id=request_id,
                document_id=data.get("document_id"),  # not present today; future-proof
                raw=data,
            )
        except KmragConflict:
            raise
        except (httpx.TransportError, httpx.HTTPStatusError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt < _retries():
                backoff = 2 ** attempt
                logger.warning("KMRAG upload retry %s/%s in %ss request_id=%s: %s",
                               attempt + 1, _retries(), backoff, request_id, type(exc).__name__)
                time.sleep(backoff)
            else:
                logger.error("KMRAG upload failed after retries request_id=%s: %s", request_id, exc)

    raise KmragUnavailable("KMRAG service is not running. Please start KMRAG and retry document upload.") from last_exc


def query_kmrag(
    *,
    tenant_id: str,
    kb_ids: list[str],
    query: str,
    request_id: str,
    user_id: str | None,
    top_k: int,
    alpha: float,
    model: str,
) -> KmragQueryResult:
    """Query KMRAG retrieval+answer. Raises KmragUnavailable on failure."""
    base = _cfg("KMRAG_BASE_URL")
    endpoint = _cfg("KMRAG_RETRIEVAL_ENDPOINT")
    url = f"{base}{endpoint}"

    payload: dict[str, Any] = {
        "query": query,
        "request_id": request_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "kb_ids": kb_ids,
        "top_k": top_k,
        "alpha": alpha,
        "model": model,
    }

    last_exc: Exception | None = None
    for attempt in range(_retries() + 1):
        try:
            with httpx.Client(timeout=_timeout()) as client:
                resp = client.post(url, json=payload, headers={"X-Request-ID": request_id})
            if resp.status_code >= 500:
                raise httpx.HTTPStatusError("kmrag 5xx", request=resp.request, response=resp)
            if resp.status_code >= 400:
                # 4xx is a rejection, not an outage — do not retry. Ownership was
                # already validated our side, so this means KMRAG can't serve
                # these KBs (usually: no ingested content yet).
                logger.warning("KMRAG query rejected %s request_id=%s body=%s",
                               resp.status_code, request_id, resp.text[:300])
                raise KmragQueryRejected("KMRAG rejected the query for the selected knowledge base(s).")

            data = resp.json()
            metadata = data.get("metadata", {}) or {}
            retrieval = (metadata.get("steps", {}) or {}).get("retrieval", {}) or {}
            sources = retrieval.get("sources", []) or metadata.get("sources", []) or []
            context_found = bool(metadata.get("context_found", bool(sources)))
            return KmragQueryResult(
                answer=data.get("answer", ""),
                context_found=context_found,
                sources=sources,
                metadata=metadata,
                request_id=data.get("request_id", request_id),
            )
        except (httpx.TransportError, httpx.HTTPStatusError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt < _retries():
                backoff = 2 ** attempt
                logger.warning("KMRAG query retry %s/%s in %ss request_id=%s: %s",
                               attempt + 1, _retries(), backoff, request_id, type(exc).__name__)
                time.sleep(backoff)
            else:
                logger.error("KMRAG query failed after retries request_id=%s: %s", request_id, exc)

    raise KmragUnavailable("The document retrieval service is temporarily unavailable. Please try again.") from last_exc


def get_kb_files(*, tenant_id: str, kb_id: str) -> list[dict] | None:
    """Return the list of files KMRAG has fully ingested for a KB, or None if the
    status could not be fetched (so callers leave document status unchanged).

    Never raises — status reconciliation must be best-effort and never break a
    document listing.
    """
    base = _cfg("KMRAG_BASE_URL")
    endpoint = _cfg("KMRAG_KB_FILES_ENDPOINT").format(kb_id=kb_id)
    url = f"{base}{endpoint}"
    try:
        # Keep the status check snappy — it runs on document-list loads.
        with httpx.Client(timeout=min(_timeout(), 10)) as client:
            resp = client.get(url, params={"tenant_id": tenant_id})
        if resp.status_code == 200:
            return list(resp.json().get("files", []))
        # 403/404/older KMRAG without this endpoint: don't reconcile.
        logger.info("KMRAG kb-files status kb=%s -> HTTP %s", kb_id, resp.status_code)
        return None
    except (httpx.TransportError, httpx.HTTPStatusError, httpx.TimeoutException) as exc:
        logger.info("KMRAG kb-files status unavailable kb=%s: %s", kb_id, type(exc).__name__)
        return None


def delete_kb_file(*, tenant_id: str, kb_id: str, file_name: str) -> bool:
    """Remove a document's vectors from KMRAG. Returns True if KMRAG confirmed the
    delete (or the file was already absent), False if KMRAG couldn't be reached.

    Never raises — deletion is best-effort so a KMRAG outage doesn't block the
    chatbot-side soft-delete. Callers should surface the returned state.
    """
    base = _cfg("KMRAG_BASE_URL")
    endpoint = _cfg("KMRAG_KB_FILES_ENDPOINT").format(kb_id=kb_id)
    url = f"{base}{endpoint}"
    try:
        with httpx.Client(timeout=min(_timeout(), 30)) as client:
            resp = client.request("DELETE", url, params={"tenant_id": tenant_id, "file_name": file_name})
        if resp.status_code == 200:
            data = resp.json()
            logger.info("KMRAG delete kb=%s file=%r -> %s", kb_id, file_name, data.get("status"))
            return True
        logger.warning("KMRAG delete kb=%s file=%r -> HTTP %s", kb_id, file_name, resp.status_code)
        return False
    except (httpx.TransportError, httpx.HTTPStatusError, httpx.TimeoutException) as exc:
        logger.warning("KMRAG delete unreachable kb=%s file=%r: %s", kb_id, file_name, type(exc).__name__)
        return False
