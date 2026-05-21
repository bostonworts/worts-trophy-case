from __future__ import annotations

import re
from pathlib import Path
from secrets import token_urlsafe

from fastapi import UploadFile

from app.core.config import settings


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
PHOTO_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
RECIPE_EXTENSIONS = {".json", ".md", ".pdf", ".txt"}


def upload_has_file(upload: UploadFile | None) -> bool:
    return upload is not None and bool(upload.filename)


def save_result_upload(
    *,
    result_id: int,
    upload: UploadFile,
    kind: str,
) -> str:
    extension = validate_upload(upload=upload, kind=kind)
    filename = safe_filename(upload.filename or f"upload{extension}")
    target_dir = upload_root() / "results" / str(result_id) / kind
    target_dir.mkdir(parents=True, exist_ok=True)

    target = target_dir / f"{token_urlsafe(10)}-{filename}"
    bytes_written = 0
    try:
        with target.open("wb") as output:
            while chunk := upload.file.read(1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_BYTES:
                    raise ValueError("Uploads must be 10 MB or smaller.")
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        upload.file.close()

    return path_to_url(target)


def delete_upload_url(url: str | None) -> None:
    if not url or not url.startswith(f"{url_prefix()}/"):
        return

    relative = url.removeprefix(f"{url_prefix()}/")
    target = (upload_root() / relative).resolve()
    root = upload_root().resolve()
    if root == target or root not in target.parents:
        return
    target.unlink(missing_ok=True)


def validate_upload(*, upload: UploadFile, kind: str) -> str:
    extension = Path(upload.filename or "").suffix.lower()
    allowed_extensions = PHOTO_EXTENSIONS if kind == "photos" else RECIPE_EXTENSIONS
    if extension not in allowed_extensions:
        if kind == "photos":
            raise ValueError("Photos must be GIF, JPEG, PNG, or WebP files.")
        raise ValueError("Recipe files must be PDF, text, Markdown, or JSON files.")
    return extension


def path_to_url(path: Path) -> str:
    relative = path.resolve().relative_to(upload_root().resolve())
    return f"{url_prefix()}/{relative.as_posix()}"


def upload_root() -> Path:
    root = Path(settings.upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def url_prefix() -> str:
    return settings.upload_url_prefix.rstrip("/")


def safe_filename(value: str) -> str:
    name = Path(value).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    if not name:
        return "upload"
    stem = Path(name).stem[:80]
    suffix = Path(name).suffix[:20]
    return f"{stem}{suffix}"
