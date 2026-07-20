"""Query-side token extraction from KMRAG /query metadata.

Shape verified against kmrag/generator/chains.py: only total_tokens/total_cost/
model exist at the top level; the input/output split lives under `steps`.
"""
from __future__ import annotations

from app.services.chat_service import _kmrag_usage


def _metadata():
    """A realistic KMRAG /query metadata payload."""
    return {
        "request_id": "r-1",
        "model": "gpt-4o-mini",
        "cache_hit": False,
        "total_tokens": 1900,
        "total_cost": 0.000431,
        "steps": {
            "embedding": {"cache_hit": False, "total_tokens": 100, "cost_usd": 0.000002},
            "manager": {
                "model": "gpt-4o-mini", "cost_usd": 0.00001,
                "usage": {"prompt_tokens": 300, "completion_tokens": 50},
            },
            "retrieval": {"documents_retrieved": 6, "sources": []},
            "generation": {
                "model": "gpt-4o-mini", "cost_usd": 0.00042,
                "usage": {"prompt_tokens": 1200, "completion_tokens": 250},
            },
        },
    }


def test_extracts_input_output_from_steps():
    usage = _kmrag_usage(_metadata())
    # input = manager prompt + generation prompt + query embedding
    assert usage["input_tokens"] == 300 + 1200 + 100
    # output = completions only (mirrors KMRAG's _QueryUsageTracker)
    assert usage["output_tokens"] == 50 + 250
    assert usage["total_tokens"] == 1900
    assert usage["total_cost"] == 0.000431
    assert usage["model"] == "gpt-4o-mini"


def test_input_reconciles_to_authoritative_total():
    # Real case: KMRAG's HTTP /query steps attribute the input a few tokens short
    # of its internal tracker (which feeds the Kafka event: tokens_input=2938,
    # tokens_output=63, quantity=3001). Output + total are authoritative, so we
    # derive input = total - output and match the Kafka event exactly.
    md = {
        "model": "gpt-4o-mini",
        "total_tokens": 3001,   # authoritative (== Kafka quantity)
        "total_cost": 0.00047452,
        "steps": {
            # step sum comes out to 2926 input, 12 short of the tracker's 2938
            "embedding": {"total_tokens": 14},
            "manager": {"usage": {"prompt_tokens": 400, "completion_tokens": 0}},
            "generation": {"usage": {"prompt_tokens": 2512, "completion_tokens": 63}},
        },
    }
    usage = _kmrag_usage(md)
    assert usage["output_tokens"] == 63
    assert usage["input_tokens"] == 2938        # 3001 - 63, matches Kafka
    assert usage["total_tokens"] == 3001
    assert usage["input_tokens"] + usage["output_tokens"] == usage["total_tokens"]


def test_no_top_level_input_output_fields_are_required():
    # Regression: reading metadata["input_tokens"] (which KMRAG never sends)
    # silently zeroed every RAG usage row.
    md = _metadata()
    assert "input_tokens" not in md and "output_tokens" not in md
    assert _kmrag_usage(md)["input_tokens"] > 0


def test_cached_answer_reports_zero_usage():
    # KMRAG zeroes totals on a cache hit — nothing was billed upstream.
    md = {
        "request_id": "r-2", "model": "gpt-4o-mini", "cache_hit": True,
        "total_tokens": 0, "total_cost": 0.0,
        "steps": {"exact_query_cache": {"hit": True}},
    }
    usage = _kmrag_usage(md)
    assert usage["total_tokens"] == 0
    assert usage["input_tokens"] == 0
    assert usage["output_tokens"] == 0


def test_falls_back_to_parts_when_total_missing():
    md = {
        "model": "gpt-4o-mini",
        "steps": {"generation": {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}},
    }
    assert _kmrag_usage(md)["total_tokens"] == 15


def test_empty_metadata_is_safe():
    assert _kmrag_usage({}) == {}
    assert _kmrag_usage(None) == {}


def test_malformed_steps_do_not_crash():
    md = {"model": "m", "total_tokens": 5, "steps": {"weird": None, "other": "string"}}
    usage = _kmrag_usage(md)
    # No usable steps, but the authoritative total stands and input reconciles
    # to it (total - output, output=0).
    assert usage["output_tokens"] == 0
    assert usage["input_tokens"] == 5
    assert usage["total_tokens"] == 5
