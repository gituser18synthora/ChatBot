"""UUID helpers used for primary keys and correlation IDs."""
from __future__ import annotations

import uuid


def new_uuid() -> str:
    """Return a new random UUID4 as a lowercase string."""
    return str(uuid.uuid4())


def is_valid_uuid(value: str | None) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False
