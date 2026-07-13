"""OpenAI client wrapper.

Used ONLY for: general (non-document) answers, lightweight query
classification, and chat-title generation. It is never used to compose RAG
answers — KMRAG already returns grounded answers.

Model names always come from config, never hardcoded in business logic.
Returns token usage so cost can be tracked centrally.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from flask import current_app
from openai import OpenAI, OpenAIError

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=current_app.config["OPENAI_API_KEY"])
    return _client


@dataclass
class ChatCompletion:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class OpenAIUnavailable(Exception):
    """OpenAI call failed. Message is safe for the frontend."""


def chat(
    *,
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int | None = None,
) -> ChatCompletion:
    model = model or current_app.config["OPENAI_CHAT_MODEL"]
    try:
        resp = _get_client().chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except OpenAIError as exc:
        logger.error("OpenAI chat error model=%s: %s", model, exc)
        raise OpenAIUnavailable("The AI service is temporarily unavailable. Please try again.") from exc

    usage = resp.usage
    return ChatCompletion(
        text=(resp.choices[0].message.content or "").strip(),
        model=model,
        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        total_tokens=getattr(usage, "total_tokens", 0) or 0,
    )
