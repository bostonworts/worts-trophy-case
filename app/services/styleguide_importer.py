from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import StyleCategory, StyleSubcategory


DEFAULT_STYLEGUIDE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "styleguides" / "bjcp_2021_beer_styles.json"
)
DEFAULT_GUIDE_YEAR = 2021
DEFAULT_SOURCE_URL = (
    "https://github.com/ascholer/bjcp-styleview/blob/main/styles.json"
)


@dataclass(frozen=True)
class StyleguideImportResult:
    categories_seen: int
    subcategories_seen: int
    categories_total: int
    subcategories_total: int


def import_styleguide(
    db: Session,
    *,
    path: Path = DEFAULT_STYLEGUIDE_PATH,
    guide_year: int = DEFAULT_GUIDE_YEAR,
) -> StyleguideImportResult:
    data = json.loads(path.read_text())
    categories_seen = 0
    subcategories_seen = 0

    for category_data in categories_from_styleguide(data):
        category = upsert_category(
            db,
            guide_year=guide_year,
            code=category_data["code"],
            name=category_data["name"],
        )
        categories_seen += 1

        for subcategory_data in category_data["subcategories"]:
            upsert_subcategory(
                db,
                category=category,
                code=subcategory_data["code"],
                name=subcategory_data["name"],
            )
            subcategories_seen += 1

    db.flush()
    return StyleguideImportResult(
        categories_seen=categories_seen,
        subcategories_seen=subcategories_seen,
        categories_total=db.scalar(select(func.count()).select_from(StyleCategory)) or 0,
        subcategories_total=db.scalar(select(func.count()).select_from(StyleSubcategory)) or 0,
    )


def categories_from_styleguide(data: dict | list[dict]) -> list[dict]:
    if isinstance(data, list):
        return categories_from_styleview(data)
    return categories_from_beerjson(data)


def categories_from_styleview(styles: list[dict]) -> list[dict]:
    categories: dict[str, dict] = {}
    for style in styles:
        category_code = style["categorynumber"]
        category = categories.setdefault(
            category_code,
            {
                "code": category_code,
                "name": normalize_category_name(style["category"]),
                "subcategories": [],
            },
        )
        category["subcategories"].append(
            {
                "code": style["number"],
                "name": style["name"],
            }
        )

    return sorted(categories.values(), key=category_sort_key)


def categories_from_beerjson(data: dict) -> list[dict]:
    categories: dict[str, dict] = {}
    for style in data["beerjson"]["styles"]:
        category_code = style["category_id"]
        category = categories.setdefault(
            category_code,
            {
                "code": category_code,
                "name": style["category"],
                "subcategories": [],
            },
        )
        category["subcategories"].append(
            {
                "code": style["style_id"],
                "name": style["name"],
            }
        )

    return sorted(categories.values(), key=category_sort_key)


def category_sort_key(category: dict) -> tuple[int, str]:
    code = category["code"]
    if code.isdigit():
        return (int(code), "")
    return (999, code)


def normalize_category_name(name: str) -> str:
    return name.replace("Ipa", "IPA")


def upsert_category(
    db: Session,
    *,
    guide_year: int,
    code: str,
    name: str,
) -> StyleCategory:
    category = db.scalar(
        select(StyleCategory).where(
            StyleCategory.guide_year == guide_year,
            StyleCategory.code == code,
        )
    )
    if category is None:
        category = StyleCategory(guide_year=guide_year, code=code, name=name)
        db.add(category)
    else:
        category.name = name
    db.flush()
    return category


def upsert_subcategory(
    db: Session,
    *,
    category: StyleCategory,
    code: str,
    name: str,
) -> StyleSubcategory:
    subcategory = db.scalar(
        select(StyleSubcategory).where(
            StyleSubcategory.category_id == category.id,
            StyleSubcategory.code == code,
        )
    )
    if subcategory is None:
        subcategory = StyleSubcategory(category=category, code=code, name=name)
        db.add(subcategory)
    else:
        subcategory.name = name
    return subcategory
