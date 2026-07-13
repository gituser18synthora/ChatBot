from __future__ import annotations

from decimal import Decimal


def test_cost_calculation(app):
    from app.services.cost_service import compute_cost
    # 1,000,000 input @ $0.15/1M + 1,000,000 output @ $0.60/1M
    costs = compute_cost("gpt-4o-mini", 1_000_000, 1_000_000)
    assert costs["input_cost_usd"] == Decimal("0.15")
    assert costs["output_cost_usd"] == Decimal("0.60")
    assert costs["total_cost_usd"] == Decimal("0.75")


def test_unknown_model_is_zero_cost(app):
    from app.services.cost_service import compute_cost
    costs = compute_cost("mystery-model", 1000, 1000)
    assert costs["total_cost_usd"] == Decimal("0")


def test_record_usage_persists(app, seed):
    from app.constants import RequestType
    from app.models.usage_log import UsageLog
    from app.services.cost_service import record_usage
    record_usage(tenant_id=seed["tenant_a"], model="gpt-4o-mini",
                 input_tokens=100, output_tokens=50, request_type=RequestType.CHAT_GENERAL)
    row = UsageLog.query.filter_by(tenant_id=seed["tenant_a"]).first()
    assert row is not None
    assert row.total_tokens == 150
