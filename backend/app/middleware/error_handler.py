"""Global error handling: turns every exception into a clean JSON envelope.

Guarantees no stack trace / SQL / KMRAG / OpenAI internal ever reaches the
client. All unexpected errors are logged with the request_id and returned as a
generic 500.
"""
from __future__ import annotations

import logging

from flask import jsonify
from werkzeug.exceptions import HTTPException

from app.integrations.kmrag_client import KmragConflict, KmragQueryRejected, KmragUnavailable
from app.integrations.openai_client import OpenAIUnavailable
from app.utils.logging_utils import get_request_id
from app.utils.response_utils import ApiError

logger = logging.getLogger(__name__)


def _envelope(code: str, message: str, status: int):
    return jsonify({"success": False, "error": {"code": code, "message": message}}), status


def register_error_handlers(app) -> None:
    @app.errorhandler(ApiError)
    def _api_error(exc: ApiError):
        return exc.to_response()

    @app.errorhandler(KmragConflict)
    def _kmrag_conflict(exc: KmragConflict):
        return _envelope("conflict", str(exc), 409)

    @app.errorhandler(KmragUnavailable)
    def _kmrag_unavailable(exc: KmragUnavailable):
        logger.warning("KMRAG unavailable request_id=%s", get_request_id())
        return _envelope("service_unavailable", str(exc), 503)

    @app.errorhandler(KmragQueryRejected)
    def _kmrag_query_rejected(_exc: KmragQueryRejected):
        # Defensive: chat_service normally handles this as a no-evidence answer.
        return _envelope(
            "no_indexed_documents",
            "The selected knowledge base(s) aren't available for search yet. If you "
            "recently uploaded documents, they may still be indexing — please try again shortly.",
            409,
        )

    @app.errorhandler(OpenAIUnavailable)
    def _openai_unavailable(exc: OpenAIUnavailable):
        logger.warning("OpenAI unavailable request_id=%s", get_request_id())
        return _envelope("service_unavailable", str(exc), 503)

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        # Werkzeug abort() / 404 / 405 / 413 (payload too large) etc.
        code = exc.name.lower().replace(" ", "_")
        message = exc.description or exc.name
        if exc.code == 413:
            message = "The uploaded file is larger than the configured limit."
        return _envelope(code, message, exc.code or 500)

    @app.errorhandler(Exception)
    def _unhandled(exc: Exception):
        logger.exception("Unhandled error request_id=%s: %s", get_request_id(), exc)
        return _envelope("internal_error", "An unexpected error occurred. Please try again.", 500)
