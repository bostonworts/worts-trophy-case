from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

from app.core.config import settings


class GoogleSheetImportError(ValueError):
    pass


def google_sheet_csv_export_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.netloc.lower() != "docs.google.com":
        raise GoogleSheetImportError("Enter a Google Sheets URL from docs.google.com.")

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 3 or path_parts[:2] != ["spreadsheets", "d"]:
        raise GoogleSheetImportError("Enter a Google Sheets URL.")

    if len(path_parts) >= 4 and path_parts[2] == "e":
        return published_sheet_csv_url(parsed)

    sheet_id = path_parts[2]
    if not sheet_id:
        raise GoogleSheetImportError("Enter a Google Sheets URL with a spreadsheet ID.")

    query = parse_qs(parsed.query)
    fragment_query = parse_qs(parsed.fragment)
    export_query = {"format": "csv"}
    gid = first_query_value(query, "gid") or first_query_value(fragment_query, "gid")
    if gid:
        export_query["gid"] = gid

    return urlunparse(
        (
            "https",
            "docs.google.com",
            f"/spreadsheets/d/{sheet_id}/export",
            "",
            urlencode(export_query),
            "",
        )
    )


def fetch_google_sheet_csv(value: str) -> bytes:
    url = google_sheet_csv_export_url(value)
    try:
        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=settings.google_sheet_fetch_timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise GoogleSheetImportError(
            "Could not download the Google Sheet. Confirm it is shared or published."
        ) from exc

    content = response.content
    if len(content) > settings.google_sheet_import_max_bytes:
        raise GoogleSheetImportError("Google Sheet CSV is too large to import.")
    if content.lstrip().startswith(b"<"):
        raise GoogleSheetImportError(
            "Google returned a web page instead of CSV. Share or publish the sheet first."
        )
    return content


def published_sheet_csv_url(parsed) -> str:
    query = parse_qs(parsed.query)
    query["output"] = ["csv"]
    path_parts = [part for part in parsed.path.split("/") if part]
    path = parsed.path
    if len(path_parts) >= 4:
        published_id = path_parts[3]
        path = f"/spreadsheets/d/e/{published_id}/pub"
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            path,
            "",
            urlencode(query, doseq=True),
            "",
        )
    )


def first_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    value = values[0].strip()
    return value or None
