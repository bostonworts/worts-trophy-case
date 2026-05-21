from __future__ import annotations

import pytest

from app.services.google_sheets import GoogleSheetImportError, google_sheet_csv_export_url


def test_google_sheet_url_converts_edit_url_to_csv_export() -> None:
    url = "https://docs.google.com/spreadsheets/d/sheet-id/edit#gid=123"

    assert google_sheet_csv_export_url(url) == (
        "https://docs.google.com/spreadsheets/d/sheet-id/export?format=csv&gid=123"
    )


def test_google_sheet_url_converts_published_url_to_csv() -> None:
    url = "https://docs.google.com/spreadsheets/d/e/published-id/pubhtml?gid=456&single=true"

    assert google_sheet_csv_export_url(url) == (
        "https://docs.google.com/spreadsheets/d/e/published-id/pub"
        "?gid=456&single=true&output=csv"
    )


def test_google_sheet_url_rejects_non_google_urls() -> None:
    with pytest.raises(GoogleSheetImportError):
        google_sheet_csv_export_url("https://example.test/sheet.csv")
