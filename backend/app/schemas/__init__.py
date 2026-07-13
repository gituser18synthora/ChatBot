"""Marshmallow request validation helpers."""
from __future__ import annotations

from flask import request
from marshmallow import Schema, ValidationError

from app.utils.response_utils import validation_error


def load_body(schema: Schema) -> dict:
    """Validate the JSON body against `schema`, returning clean data or raising
    a frontend-safe ApiError listing the first problem."""
    payload = request.get_json(silent=True) or {}
    try:
        return schema.load(payload)
    except ValidationError as exc:
        first = next(iter(exc.messages.values()))
        msg = first[0] if isinstance(first, list) else str(first)
        field = next(iter(exc.messages))
        raise validation_error(f"{field}: {msg}")


def load_query(schema: Schema) -> dict:
    try:
        return schema.load(request.args.to_dict())
    except ValidationError as exc:
        first = next(iter(exc.messages.values()))
        msg = first[0] if isinstance(first, list) else str(first)
        raise validation_error(str(msg))
