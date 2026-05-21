from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.core.config import settings


HTTP_SCHEMES = {"http", "https"}


def blank_to_none(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def validate_link_url(
    value: Any,
    *,
    field_label: str,
    max_length: int = 500,
    allow_upload_path: bool = False,
) -> tuple[str | None, str | None]:
    cleaned = blank_to_none(value)
    if cleaned is None:
        return None, None
    if len(cleaned) > max_length:
        return cleaned, f"{field_label} must be {max_length} characters or fewer."
    if is_allowed_link_url(cleaned, allow_upload_path=allow_upload_path):
        return cleaned, None
    if allow_upload_path:
        return (
            cleaned,
            f"{field_label} must be an http(s) URL or a local upload path.",
        )
    return cleaned, f"{field_label} must be an http(s) URL."


def is_allowed_link_url(value: str, *, allow_upload_path: bool = False) -> bool:
    parsed = urlparse(value)
    if parsed.scheme in HTTP_SCHEMES and bool(parsed.netloc):
        return True
    return allow_upload_path and is_local_upload_url(value)


def is_local_upload_url(value: str) -> bool:
    prefix = settings.upload_url_prefix.rstrip("/")
    return value.startswith(f"{prefix}/") and not value.startswith("//")
