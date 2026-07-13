"""Centralized OpenAI cost calculation and usage logging.

Pricing comes from config (MODEL_PRICING_JSON) — never hardcoded here.
Costs are computed at full decimal precision and only rounded for display.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from flask import current_app

from app.constants import RequestType
from app.extensions import db
from app.models.usage_log import UsageLog

logger = logging.getLogger(__name__)

_MILLION = Decimal(1_000_000)


def _price(model: str) -> tuple[Decimal, Decimal]:
    """Return (input_per_1m, output_per_1m) as Decimals. Unknown model -> (0,0)."""
    pricing = current_app.config.get("MODEL_PRICING", {}) or {}
    entry = pricing.get(model)
    if not entry:
        logger.warning("No pricing configured for model=%s; cost recorded as 0", model)
        return Decimal(0), Decimal(0)
    return (
        Decimal(str(entry.get("input_per_1m_tokens", 0))),
        Decimal(str(entry.get("output_per_1m_tokens", 0))),
    )


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> dict:
    in_price, out_price = _price(model)
    input_cost = (Decimal(input_tokens) / _MILLION) * in_price
    output_cost = (Decimal(output_tokens) / _MILLION) * out_price
    total_cost = input_cost + output_cost
    return {
        "input_cost_usd": input_cost,
        "output_cost_usd": output_cost,
        "total_cost_usd": total_cost,
    }


def record_usage(
    *,
    tenant_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    request_type: str = RequestType.CHAT_GENERAL,
    user_id: str | None = None,
    chat_session_id: str | None = None,
    latency_ms: int | None = None,
    commit: bool = True,
) -> UsageLog:
    """Persist a usage/cost row. Does NOT swallow DB errors — caller decides."""
    costs = compute_cost(model, input_tokens, output_tokens)
    log = UsageLog(
        tenant_id=tenant_id,
        user_id=user_id,
        chat_session_id=chat_session_id,
        request_type=request_type,
        model_name=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        input_cost_usd=costs["input_cost_usd"],
        output_cost_usd=costs["output_cost_usd"],
        total_cost_usd=costs["total_cost_usd"],
        latency_ms=latency_ms,
    )
    db.session.add(log)
    if commit:
        db.session.commit()
    return log
