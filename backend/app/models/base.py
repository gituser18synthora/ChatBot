"""Shared model plumbing: portable UUID column + timestamp mixin.

Uses CHAR(36) UUID strings so the same models run on MySQL (production) and
SQLite (tests) without dialect-specific types.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CHAR, DateTime, String
from sqlalchemy.sql import func

from app.extensions import db
from app.utils.uuid_utils import new_uuid


class GUID(CHAR):
    """UUID stored as a 36-char string. Portable across MySQL and SQLite."""

    def __init__(self):
        super().__init__(36)


def uuid_pk():
    return db.Column(GUID(), primary_key=True, default=new_uuid)


def uuid_fk(target: str, nullable: bool = False, index: bool = True):
    return db.Column(GUID(), db.ForeignKey(target, ondelete="CASCADE"), nullable=nullable, index=index)


class TimestampMixin:
    created_at = db.Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = db.Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


def utcnow() -> datetime:
    return datetime.utcnow()


__all__ = ["GUID", "uuid_pk", "uuid_fk", "TimestampMixin", "utcnow", "String"]
