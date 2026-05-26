from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Competition, Result
from app.db.session import get_db
from app.domain.scoring import LeaderboardBreakdown, leaderboard_breakdown
from app.domain.seasons import Season
from app.services.leaderboard_settings import load_leaderboard_settings
from app.templating import templates

router = APIRouter()


@router.get("/leaderboard", response_class=HTMLResponse)
def show(
    request: Request,
    season: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    settings = load_leaderboard_settings(db)
    try:
        selected_season = (
            Season.from_param(
                season,
                start_month=settings.season_start_month,
                start_day=settings.season_start_day,
            )
            if season
            else Season.current(
                start_month=settings.season_start_month,
                start_day=settings.season_start_day,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="season must use YYYY-YYYY.") from exc
    results = db.scalars(
        select(Result)
        .join(Result.competition)
        .options(selectinload(Result.member), selectinload(Result.competition))
        .where(Competition.date >= selected_season.start_date)
        .where(Competition.date < selected_season.end_boundary)
        .where(Result.archived_at.is_(None))
        .where(Competition.archived_at.is_(None))
    ).all()

    totals: dict[int, dict[str, Decimal | int | str]] = {}
    breakdown_rows = []
    for result in results:
        breakdown = leaderboard_breakdown(
            place=result.place,
            placement_scope=result.placement_scope,
            competition_type=result.competition.competition_type,
            bjcp_score=result.bjcp_score,
            settings=settings,
        )
        if breakdown.total == 0:
            continue
        row = totals.setdefault(
            result.member_id,
            {
                "member_id": result.member_id,
                "display_name": result.member.display_name,
                "points": Decimal("0"),
            },
        )
        row["points"] = row["points"] + breakdown.total
        breakdown_rows.append(
            {
                "member": result.member.display_name,
                "competition": result.competition.name,
                "place": result.place,
                "scope": result.placement_scope.value if result.placement_scope else "",
                "breakdown": breakdown,
                "formula": leaderboard_formula(breakdown),
            }
        )

    rows = sorted(totals.values(), key=lambda row: (-row["points"], row["display_name"]))

    seasons = sorted(
        {
            Season.for_date(
                value,
                start_month=settings.season_start_month,
                start_day=settings.season_start_day,
            )
            for value in db.scalars(
                select(Competition.date).where(Competition.archived_at.is_(None))
            ).all()
        }
        | {
            Season.current(
                start_month=settings.season_start_month,
                start_day=settings.season_start_day,
            )
        },
        reverse=True,
    )

    return templates.TemplateResponse(
        request,
        "leaderboard/show.html",
        {
            "rows": rows,
            "selected_season": selected_season,
            "seasons": seasons,
            "settings": settings,
            "breakdown_rows": breakdown_rows[:20],
        },
    )


def leaderboard_formula(breakdown: LeaderboardBreakdown) -> str:
    return (
        f"({breakdown.base_points} x placement multiplier "
        f"{breakdown.placement_multiplier} + high-profile bonus "
        f"{breakdown.high_profile_bonus}) x competition weight "
        f"{breakdown.competition_weight}"
    )
