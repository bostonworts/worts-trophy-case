from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Competition, Result, StyleCategory, StyleSubcategory
from app.db.session import get_db
from app.domain.scoring import leaderboard_points
from app.services.leaderboard_settings import load_leaderboard_settings
from app.templating import templates

router = APIRouter()


@router.get("/styles", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    categories = db.scalars(
        select(StyleCategory).options(selectinload(StyleCategory.subcategories))
    ).all()
    result_counts = active_result_counts_by_category(db)
    category_rows = [
        {
            "category": category,
            "subcategory_count": len(category.subcategories),
            "result_count": result_counts.get(category.id, 0),
        }
        for category in sorted(categories, key=lambda category: style_code_key(category.code))
    ]
    return templates.TemplateResponse(
        request,
        "styles/index.html",
        {"category_rows": category_rows},
    )


@router.get("/styles/subcategories/{subcategory_id}", response_class=HTMLResponse)
def show_subcategory(
    subcategory_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    subcategory = db.scalar(
        select(StyleSubcategory)
        .options(selectinload(StyleSubcategory.category))
        .where(StyleSubcategory.id == subcategory_id)
    )
    if subcategory is None:
        raise HTTPException(status_code=404, detail="Style not found")

    current_member = request.state.current_member
    is_admin = current_member is not None and current_member.is_admin
    active_results = db.scalars(
        style_results_query(style_subcategory_id=subcategory.id)
        .where(Result.archived_at.is_(None))
        .where(Competition.archived_at.is_(None))
    ).all()
    archived_results = []
    if is_admin:
        archived_results = db.scalars(
            style_results_query(style_subcategory_id=subcategory.id).where(
                (Result.archived_at.is_not(None)) | (Competition.archived_at.is_not(None))
            )
        ).all()

    leaderboard_settings = load_leaderboard_settings(db)
    active_rows = result_rows(active_results, settings=leaderboard_settings)
    archived_rows = result_rows(archived_results, settings=leaderboard_settings)
    stats = result_stats(active_rows)
    return templates.TemplateResponse(
        request,
        "styles/subcategory.html",
        {
            "subcategory": subcategory,
            "active_rows": active_rows,
            "archived_rows": archived_rows,
            "stats": stats,
        },
    )


@router.get("/styles/{category_id}", response_class=HTMLResponse)
def show_category(
    category_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    category = db.scalar(
        select(StyleCategory)
        .options(selectinload(StyleCategory.subcategories))
        .where(StyleCategory.id == category_id)
    )
    if category is None:
        raise HTTPException(status_code=404, detail="Style category not found")

    current_member = request.state.current_member
    is_admin = current_member is not None and current_member.is_admin
    active_results = db.scalars(
        style_results_query(category_id=category.id)
        .where(Result.archived_at.is_(None))
        .where(Competition.archived_at.is_(None))
    ).all()
    archived_results = []
    if is_admin:
        archived_results = db.scalars(
            style_results_query(category_id=category.id).where(
                (Result.archived_at.is_not(None)) | (Competition.archived_at.is_not(None))
            )
        ).all()

    subcategory_counts = active_result_counts_by_subcategory(
        db,
        [subcategory.id for subcategory in category.subcategories],
    )
    subcategory_rows = [
        {
            "subcategory": subcategory,
            "result_count": subcategory_counts.get(subcategory.id, 0),
        }
        for subcategory in sorted(
            category.subcategories,
            key=lambda subcategory: style_code_key(subcategory.code),
        )
    ]
    leaderboard_settings = load_leaderboard_settings(db)
    active_rows = result_rows(active_results, settings=leaderboard_settings)
    archived_rows = result_rows(archived_results, settings=leaderboard_settings)
    stats = result_stats(active_rows)
    return templates.TemplateResponse(
        request,
        "styles/show.html",
        {
            "category": category,
            "subcategory_rows": subcategory_rows,
            "active_rows": active_rows,
            "archived_rows": archived_rows,
            "stats": stats,
        },
    )


def style_results_query(
    *,
    category_id: int | None = None,
    style_subcategory_id: int | None = None,
):
    query = (
        select(Result)
        .join(Result.competition)
        .join(Result.style_subcategory)
        .options(
            selectinload(Result.member),
            selectinload(Result.competition),
            selectinload(Result.style_subcategory).selectinload(StyleSubcategory.category),
        )
        .order_by(Competition.date.desc(), Result.created_at.desc())
    )
    if category_id is not None:
        query = query.where(StyleSubcategory.category_id == category_id)
    if style_subcategory_id is not None:
        query = query.where(Result.style_subcategory_id == style_subcategory_id)
    return query


def active_result_counts_by_category(db: Session) -> dict[int, int]:
    return {
        category_id: result_count
        for category_id, result_count in db.execute(
            select(StyleSubcategory.category_id, func.count(Result.id))
            .join(Result, Result.style_subcategory_id == StyleSubcategory.id)
            .join(Result.competition)
            .where(Result.archived_at.is_(None))
            .where(Competition.archived_at.is_(None))
            .group_by(StyleSubcategory.category_id)
        ).all()
    }


def active_result_counts_by_subcategory(
    db: Session,
    subcategory_ids: list[int],
) -> dict[int, int]:
    if not subcategory_ids:
        return {}
    return {
        style_subcategory_id: result_count
        for style_subcategory_id, result_count in db.execute(
            select(Result.style_subcategory_id, func.count(Result.id))
            .join(Result.competition)
            .where(Result.archived_at.is_(None))
            .where(Competition.archived_at.is_(None))
            .where(Result.style_subcategory_id.in_(subcategory_ids))
            .group_by(Result.style_subcategory_id)
        ).all()
    }


def result_rows(results: list[Result], *, settings) -> list[dict[str, Decimal | Result | str]]:
    rows = []
    for result in results:
        rows.append(
            {
                "result": result,
                "points": leaderboard_points(
                    place=result.place,
                    placement_scope=result.placement_scope,
                    competition_type=result.competition.competition_type,
                    bjcp_score=result.bjcp_score,
                    settings=settings,
                ),
                "hidden_reason": hidden_result_reason(result),
            }
        )
    return rows


def result_stats(rows: list[dict[str, Decimal | Result | str]]) -> dict[str, Decimal | int | str]:
    scores = [
        row["result"].bjcp_score
        for row in rows
        if isinstance(row["result"], Result) and row["result"].bjcp_score is not None
    ]
    return {
        "result_count": len(rows),
        "placed_count": sum(
            1
            for row in rows
            if isinstance(row["result"], Result) and row["result"].place is not None
        ),
        "points": sum(
            (row["points"] for row in rows if isinstance(row["points"], Decimal)),
            Decimal("0"),
        ),
        "best_score": max(scores) if scores else "None",
    }


def hidden_result_reason(result: Result) -> str:
    if result.archived_at is not None:
        return "Result archived"
    if result.competition.archived_at is not None:
        return "Competition archived"
    return ""


def style_code_key(value: str) -> tuple[int, str]:
    digits = ""
    suffix = ""
    for character in value:
        if character.isdigit() and not suffix:
            digits += character
        else:
            suffix += character
    return (int(digits) if digits else 0, suffix)
