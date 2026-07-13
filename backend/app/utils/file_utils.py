"""Upload validation helpers (extension, size, MIME)."""
from __future__ import annotations

import os

from app.utils.response_utils import ApiError, validation_error

# Minimal, safe extension -> content-type map for allowed types.
_EXT_CONTENT_TYPE = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}


def get_extension(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lstrip(".").lower()


def validate_upload(filename: str, size_bytes: int, allowed_exts: set[str], max_bytes: int) -> str:
    """Validate an upload and return its resolved content-type.

    Raises ApiError with a clean, frontend-safe message on any violation.
    """
    if not filename:
        raise validation_error("No file was provided.")

    ext = get_extension(filename)
    if ext not in allowed_exts:
        raise ApiError(
            "Please upload a supported document type "
            f"({', '.join(sorted(allowed_exts))}).",
            422,
            "unsupported_file_type",
        )

    if size_bytes <= 0:
        raise validation_error("The uploaded file is empty.")

    if size_bytes > max_bytes:
        raise ApiError(
            f"The uploaded file is larger than the configured limit "
            f"({max_bytes // (1024 * 1024)} MB).",
            413,
            "file_too_large",
        )

    return _EXT_CONTENT_TYPE.get(ext, "application/octet-stream")
