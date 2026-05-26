from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from decimal import InvalidOperation
from io import StringIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_admin
from app.db.models import (
    AuditLog,
    Competition,
    CompetitionType,
    Member,
    PlacementScope,
    Result,
    StyleCategory,
    StyleSubcategory,
)
from app.db.session import get_db
from app.domain.scoring import leaderboard_breakdown, leaderboard_points
from app.domain.seasons import Season
from app.services.audit import record_audit
from app.services.leaderboard_settings import load_leaderboard_settings
from app.services.placements import parse_place_value
from app.services.member_auth import ensure_primary_email_alias
from app.services.uploads import delete_upload_url, save_result_upload, upload_has_file
from app.services.urls import validate_link_url
from app.templating import templates

router = APIRouter()

PLACEMENT_FILTERS = {
    "placed": "Placed",
    "unplaced": "Unplaced",
}

RESULT_IMPORT_COLUMNS = {
    "id",
    "member_email",
    "member_display_name",
    "competition_name",
    "competition_date",
    "competition_type",
    "style_guide_year",
    "style_category_code",
    "style_category_name",
    "style_subcategory_code",
    "style_subcategory_name",
    "bjcp_score",
    "place",
    "placement_scope",
    "leaderboard_points",
    "recipe_url",
    "recipe_file_url",
    "photo_url",
    "notes",
    "result_status",
    "result_archived_at",
    "competition_archived_at",
    "created_at",
    "updated_at",
}


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/leaderboard", status_code=303)


@router.get("/results", response_class=HTMLResponse)
def index(
    request: Request,
    season: str | None = Query(None),
    member_id: str | None = Query(None),
    competition_id: str | None = Query(None),
    category_id: str | None = Query(None),
    style_subcategory_id: str | None = Query(None),
    placement: str | None = Query(None),
    q: str | None = Query(None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    current_member = request.state.current_member
    is_admin = current_member is not None and current_member.is_admin
    leaderboard_settings = load_leaderboard_settings(db)
    selected_season = parse_season_param(season, settings=leaderboard_settings)
    selected_member_id = parse_optional_int_query(member_id, "member_id")
    selected_competition_id = parse_optional_int_query(competition_id, "competition_id")
    selected_category_id = parse_optional_int_query(category_id, "category_id")
    selected_style_subcategory_id = parse_optional_int_query(
        style_subcategory_id,
        "style_subcategory_id",
    )
    selected_placement = placement if placement in PLACEMENT_FILTERS else None
    search_query = q.strip() if q and q.strip() else None

    active_results_query = apply_result_filters(
        select(Result)
        .join(Result.competition)
        .options(
            selectinload(Result.member),
            selectinload(Result.competition),
            selectinload(Result.style_subcategory).selectinload(StyleSubcategory.category),
        )
        .where(Result.archived_at.is_(None))
        .where(Competition.archived_at.is_(None))
        .order_by(Competition.date.desc(), Result.created_at.desc()),
        selected_season=selected_season,
        selected_member_id=selected_member_id,
        selected_competition_id=selected_competition_id,
        selected_category_id=selected_category_id,
        selected_style_subcategory_id=selected_style_subcategory_id,
        selected_placement=selected_placement,
        search_query=search_query,
    )
    active_results = db.scalars(active_results_query).all()
    archived_results = []
    if is_admin:
        archived_results_query = apply_result_filters(
            select(Result)
            .join(Result.competition)
            .options(
                selectinload(Result.member),
                selectinload(Result.competition),
                selectinload(Result.style_subcategory).selectinload(StyleSubcategory.category),
            )
            .where(or_(Result.archived_at.is_not(None), Competition.archived_at.is_not(None)))
            .order_by(Competition.date.desc(), Result.created_at.desc()),
            selected_season=selected_season,
            selected_member_id=selected_member_id,
            selected_competition_id=selected_competition_id,
            selected_category_id=selected_category_id,
            selected_style_subcategory_id=selected_style_subcategory_id,
            selected_placement=selected_placement,
            search_query=search_query,
        )
        archived_results = db.scalars(archived_results_query).all()

    seasons = available_seasons(
        db,
        include_archived=is_admin,
        settings=leaderboard_settings,
    )
    if selected_season is not None and selected_season not in seasons:
        seasons = sorted([*seasons, selected_season], reverse=True)
    members = db.scalars(select(Member).order_by(Member.display_name)).all()
    competitions_query = select(Competition).order_by(Competition.date.desc(), Competition.name)
    if not is_admin:
        competitions_query = competitions_query.where(Competition.archived_at.is_(None))
    competitions = db.scalars(competitions_query).all()
    categories = db.scalars(
        select(StyleCategory).order_by(StyleCategory.guide_year.desc(), StyleCategory.code)
    ).all()
    filters_active = any(
        [
            selected_season,
            selected_member_id,
            selected_competition_id,
            selected_category_id,
            selected_style_subcategory_id,
            selected_placement,
            search_query,
        ]
    )
    return templates.TemplateResponse(
        request,
        "results/index.html",
        {
            "active_results": active_results,
            "archived_results": archived_results,
            "archive_stats": result_archive_stats(active_results),
            "seasons": seasons,
            "members": members,
            "competitions": competitions,
            "categories": categories,
            "placement_filters": PLACEMENT_FILTERS,
            "filters": {
                "season": selected_season,
                "member_id": selected_member_id,
                "competition_id": selected_competition_id,
                "category_id": selected_category_id,
                "style_subcategory_id": selected_style_subcategory_id,
                "placement": selected_placement,
                "q": search_query or "",
            },
            "filters_active": filters_active,
        },
    )


@router.get("/results/new", response_class=HTMLResponse)
def new(
    request: Request,
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> HTMLResponse:
    return render_form(request, db)


@router.get("/results/import", response_class=HTMLResponse)
def import_form(
    request: Request,
    _admin: Member = Depends(require_admin),
) -> HTMLResponse:
    return render_import(request)


@router.get("/results.csv")
def export_results(
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> Response:
    leaderboard_settings = load_leaderboard_settings(db)
    results = db.scalars(
        select(Result)
        .join(Result.competition)
        .options(
            selectinload(Result.member),
            selectinload(Result.competition),
            selectinload(Result.style_subcategory).selectinload(StyleSubcategory.category),
        )
        .order_by(Competition.date.desc(), Result.created_at.desc())
    ).all()
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "member_email",
            "member_display_name",
            "competition_name",
            "competition_date",
            "competition_type",
            "style_category_code",
            "style_category_name",
            "style_subcategory_code",
            "style_subcategory_name",
            "bjcp_score",
            "place",
            "placement_scope",
            "leaderboard_points",
            "recipe_url",
            "recipe_file_url",
            "photo_url",
            "notes",
            "result_archived_at",
            "competition_archived_at",
            "created_at",
            "updated_at",
        ],
    )
    writer.writeheader()
    for result in results:
        points = leaderboard_points(
            place=result.place,
            placement_scope=result.placement_scope,
            competition_type=result.competition.competition_type,
            bjcp_score=result.bjcp_score,
            settings=leaderboard_settings,
        )
        writer.writerow(
            {
                "id": result.id,
                "member_email": result.member.email,
                "member_display_name": result.member.display_name,
                "competition_name": result.competition.name,
                "competition_date": result.competition.date.isoformat(),
                "competition_type": result.competition.competition_type.value,
                "style_category_code": result.style_subcategory.category.code,
                "style_category_name": result.style_subcategory.category.name,
                "style_subcategory_code": result.style_subcategory.code,
                "style_subcategory_name": result.style_subcategory.name,
                "bjcp_score": result.bjcp_score or "",
                "place": result.place or "",
                "placement_scope": result.placement_scope.value if result.placement_scope else "",
                "leaderboard_points": points,
                "recipe_url": result.recipe_url or "",
                "recipe_file_url": result.recipe_file_url or "",
                "photo_url": result.photo_url or "",
                "notes": result.notes or "",
                "result_archived_at": isoformat_or_empty(result.archived_at),
                "competition_archived_at": isoformat_or_empty(result.competition.archived_at),
                "created_at": isoformat_or_empty(result.created_at),
                "updated_at": isoformat_or_empty(result.updated_at),
            }
        )
    return csv_response(output.getvalue(), filename="results.csv")


@router.post("/results/import", response_class=HTMLResponse)
def import_results(
    request: Request,
    csv_file: UploadFile = File(...),
    action: str = Form("import"),
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> HTMLResponse:
    content = csv_file.file.read()
    csv_file.file.close()
    resolution_counts = {"members": 0, "competitions": 0, "styles": 0}
    plan, errors = parse_result_import(
        db,
        content,
        create_missing_references=action == "resolve",
        resolution_counts=resolution_counts,
    )
    if errors:
        if action == "resolve":
            db.rollback()
        return render_import(request, errors=errors, status_code=400)

    preview = analyze_result_import(db, plan)
    if action == "preview":
        return render_import(
            request,
            summary=preview_summary("results", preview),
            preview=preview,
        )

    created = 0
    skipped = 0
    seen_keys: set[tuple[object, ...]] = set()
    for row in plan:
        key = result_import_key(row)
        if key in seen_keys or result_duplicate_exists(db, row):
            skipped += 1
            continue
        seen_keys.add(key)
        db.add(
            Result(
                member_id=row.member_id,
                competition_id=row.competition_id,
                style_subcategory_id=row.style_subcategory_id,
                bjcp_score=row.bjcp_score,
                place=row.place,
                placement_scope=row.placement_scope,
                recipe_url=row.recipe_url,
                recipe_file_url=row.recipe_file_url,
                photo_url=row.photo_url,
                notes=row.notes,
                archived_at=datetime.now(UTC) if row.archived else None,
            )
        )
        created += 1
    record_audit(
        db,
        actor=admin,
        action="import",
        entity_type="results",
        entity_id=None,
        summary=f"Imported {created} results; skipped {skipped} likely duplicates.",
        metadata={
            "created": created,
            "skipped": skipped,
            "resolved": resolution_counts,
        },
    )
    db.commit()
    summary = f"Imported {created} results."
    if skipped:
        summary += f" Skipped {skipped} likely duplicates."
    if action == "resolve":
        summary += (
            " Resolved "
            f"{resolution_counts['members']} members, "
            f"{resolution_counts['competitions']} competitions, and "
            f"{resolution_counts['styles']} styles."
        )
    return render_import(request, summary=summary)


@router.get("/results/{result_id}", response_class=HTMLResponse)
def show(result_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    result = load_result_detail_or_404(db, result_id)
    current_member = request.state.current_member
    is_admin = current_member is not None and current_member.is_admin
    if not is_admin and (
        result.archived_at is not None or result.competition.archived_at is not None
    ):
        raise HTTPException(status_code=404, detail="Result not found")

    audit_entries = []
    if is_admin:
        audit_entries = db.scalars(
            select(AuditLog)
            .options(selectinload(AuditLog.actor))
            .where(AuditLog.entity_type == "result", AuditLog.entity_id == result.id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        ).all()

    breakdown = leaderboard_breakdown(
        place=result.place,
        placement_scope=result.placement_scope,
        competition_type=result.competition.competition_type,
        bjcp_score=result.bjcp_score,
        settings=load_leaderboard_settings(db),
    )
    return templates.TemplateResponse(
        request,
        "results/show.html",
        {
            "result": result,
            "points": breakdown.total,
            "breakdown": breakdown,
            "audit_entries": audit_entries,
        },
    )


@router.get("/results/{result_id}/edit", response_class=HTMLResponse)
def edit(
    result_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _admin: Member = Depends(require_admin),
) -> HTMLResponse:
    result = get_result_or_404(db, result_id)
    return render_form(
        request,
        db,
        form=result_form(result),
        selected_member_id=result.member_id,
        selected_competition_id=result.competition_id,
        form_action=f"/results/{result.id}",
        page_title="Edit Result",
        page_heading="Edit result",
        submit_label="Save Changes",
    )


@router.post("/results")
def create(
    request: Request,
    member_id: int | None = Form(None),
    competition_id: int | None = Form(None),
    style_subcategory_id: int | None = Form(None),
    bjcp_score: Decimal | None = Form(None),
    place: int | None = Form(None),
    placement_scope: PlacementScope | None = Form(None),
    recipe_url: str | None = Form(None),
    recipe_file: UploadFile | None = File(None),
    photo: UploadFile | None = File(None),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> Response:
    form = result_submission_form(
        member_id=member_id,
        competition_id=competition_id,
        style_subcategory_id=style_subcategory_id,
        bjcp_score=bjcp_score,
        place=place,
        placement_scope=placement_scope,
        recipe_url=recipe_url,
        notes=notes,
    )
    errors = validate_result(
        db,
        member_id=member_id,
        competition_id=competition_id,
        style_subcategory_id=style_subcategory_id,
        bjcp_score=bjcp_score,
        place=place,
        placement_scope=placement_scope,
        recipe_url=recipe_url,
    )
    if errors:
        return render_form(request, db, form=form, errors=errors, status_code=400)

    assert member_id is not None
    assert competition_id is not None
    assert style_subcategory_id is not None
    result = Result(
        member_id=member_id,
        competition_id=competition_id,
        style_subcategory_id=style_subcategory_id,
        bjcp_score=bjcp_score,
        place=place,
        placement_scope=placement_scope,
        recipe_url=blank_to_none(recipe_url),
        notes=blank_to_none(notes),
    )
    db.add(result)
    db.flush()
    attachment_errors = save_result_attachments(result, photo=photo, recipe_file=recipe_file)
    if attachment_errors:
        db.rollback()
        return render_form(
            request,
            db,
            form=form,
            errors=attachment_errors,
            status_code=400,
        )
    record_audit(
        db,
        actor=admin,
        action="create",
        entity_type="result",
        entity_id=result.id,
        summary="Created result.",
        metadata=result_audit_metadata(result),
    )
    db.commit()
    return RedirectResponse("/results", status_code=303)


@router.post("/results/{result_id}")
def update(
    result_id: int,
    request: Request,
    member_id: int | None = Form(None),
    competition_id: int | None = Form(None),
    style_subcategory_id: int | None = Form(None),
    bjcp_score: Decimal | None = Form(None),
    place: int | None = Form(None),
    placement_scope: PlacementScope | None = Form(None),
    recipe_url: str | None = Form(None),
    recipe_file: UploadFile | None = File(None),
    photo: UploadFile | None = File(None),
    remove_recipe_file: bool = Form(False),
    remove_photo: bool = Form(False),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> Response:
    result = get_result_or_404(db, result_id)
    form = result_submission_form(
        member_id=member_id,
        competition_id=competition_id,
        style_subcategory_id=style_subcategory_id,
        bjcp_score=bjcp_score,
        place=place,
        placement_scope=placement_scope,
        recipe_url=recipe_url,
        notes=notes,
    )
    form["photo_url"] = result.photo_url or ""
    form["recipe_file_url"] = result.recipe_file_url or ""
    errors = validate_result(
        db,
        member_id=member_id,
        competition_id=competition_id,
        style_subcategory_id=style_subcategory_id,
        bjcp_score=bjcp_score,
        place=place,
        placement_scope=placement_scope,
        recipe_url=recipe_url,
        allow_inactive_member_id=result.member_id,
        allow_archived_competition_id=result.competition_id,
    )
    if errors:
        return render_form(
            request,
            db,
            form=form,
            errors=errors,
            selected_member_id=member_id,
            selected_competition_id=competition_id,
            form_action=f"/results/{result.id}",
            page_title="Edit Result",
            page_heading="Edit result",
            submit_label="Save Changes",
            status_code=400,
        )

    assert member_id is not None
    assert competition_id is not None
    assert style_subcategory_id is not None
    result.member_id = member_id
    result.competition_id = competition_id
    result.style_subcategory_id = style_subcategory_id
    result.bjcp_score = bjcp_score
    result.place = place
    result.placement_scope = placement_scope
    result.recipe_url = blank_to_none(recipe_url)
    result.notes = blank_to_none(notes)
    attachment_errors = update_result_attachments(
        result,
        photo=photo,
        recipe_file=recipe_file,
        remove_photo=remove_photo,
        remove_recipe_file=remove_recipe_file,
    )
    if attachment_errors:
        return render_form(
            request,
            db,
            form=form,
            errors=attachment_errors,
            selected_member_id=member_id,
            selected_competition_id=competition_id,
            form_action=f"/results/{result.id}",
            page_title="Edit Result",
            page_heading="Edit result",
            submit_label="Save Changes",
            status_code=400,
        )
    record_audit(
        db,
        actor=admin,
        action="update",
        entity_type="result",
        entity_id=result.id,
        summary="Updated result.",
        metadata=result_audit_metadata(result),
    )
    db.commit()
    return RedirectResponse("/results", status_code=303)


@router.post("/results/{result_id}/archive")
def archive(
    result_id: int,
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> RedirectResponse:
    result = get_result_or_404(db, result_id)
    result.archived_at = datetime.now(UTC)
    record_audit(
        db,
        actor=admin,
        action="archive",
        entity_type="result",
        entity_id=result.id,
        summary="Archived result.",
        metadata=result_audit_metadata(result),
    )
    db.commit()
    return RedirectResponse("/results", status_code=303)


@router.post("/results/{result_id}/restore")
def restore(
    result_id: int,
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> RedirectResponse:
    result = get_result_or_404(db, result_id)
    result.archived_at = None
    record_audit(
        db,
        actor=admin,
        action="restore",
        entity_type="result",
        entity_id=result.id,
        summary="Restored result.",
        metadata=result_audit_metadata(result),
    )
    db.commit()
    return RedirectResponse("/results", status_code=303)


def render_form(
    request: Request,
    db: Session,
    *,
    form: dict[str, str] | None = None,
    errors: list[str] | None = None,
    selected_member_id: int | None = None,
    selected_competition_id: int | None = None,
    form_action: str = "/results",
    page_title: str = "Add Result",
    page_heading: str = "Add result",
    submit_label: str = "Save Result",
    member_locked: Member | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    if member_locked is not None:
        members = [member_locked]
        selected_member_id = member_locked.id
        form = {**(form or {}), "member_id": str(member_locked.id)}
    else:
        members = db.scalars(
            select(Member)
            .where(Member.deactivated_at.is_(None))
            .order_by(Member.display_name)
        ).all()
        if selected_member_id is not None and all(
            member.id != selected_member_id for member in members
        ):
            selected_member = db.get(Member, selected_member_id)
            if selected_member is not None:
                members = [selected_member, *members]
    competitions = db.scalars(
        select(Competition)
        .where(Competition.archived_at.is_(None))
        .order_by(Competition.date.desc())
    ).all()
    if selected_competition_id is not None and all(
        competition.id != selected_competition_id for competition in competitions
    ):
        selected_competition = db.get(Competition, selected_competition_id)
        if selected_competition is not None:
            competitions = [selected_competition, *competitions]
    subcategories = db.scalars(
        select(StyleSubcategory)
        .join(StyleSubcategory.category)
        .options(selectinload(StyleSubcategory.category))
        .order_by(StyleCategory.guide_year.desc(), StyleCategory.code, StyleSubcategory.code)
    ).all()
    return templates.TemplateResponse(
        request,
        "results/new.html",
        {
            "members": members,
            "competitions": competitions,
            "subcategories": subcategories,
            "placement_scopes": list(PlacementScope),
            "form": form or {},
            "errors": errors or [],
            "form_action": form_action,
            "page_title": page_title,
            "page_heading": page_heading,
            "submit_label": submit_label,
            "member_locked": member_locked,
        },
        status_code=status_code,
    )


def render_import(
    request: Request,
    *,
    errors: list[str] | None = None,
    summary: str | None = None,
    preview: dict[str, object] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "results/import.html",
        {
            "errors": errors or [],
            "summary": summary,
            "columns": [
                "member_email",
                "competition_name",
                "competition_date",
                "style_subcategory_code",
                "style_guide_year",
                "bjcp_score",
                "place",
                "placement_scope",
                "recipe_url",
                "notes",
                "result_status",
            ],
            "placement_scopes": [placement_scope.value for placement_scope in PlacementScope],
            "preview": preview,
        },
        status_code=status_code,
    )


def parse_season_param(
    value: str | None,
    *,
    settings,
) -> Season | None:
    if not value:
        return None
    try:
        return Season.from_param(
            value,
            start_month=settings.season_start_month,
            start_day=settings.season_start_day,
        )
    except ValueError:
        return None


def parse_optional_int_query(value: str | None, name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"{name} must be an integer.",
        ) from exc


def available_seasons(
    db: Session,
    *,
    include_archived: bool,
    settings,
) -> list[Season]:
    query = select(Competition.date)
    if not include_archived:
        query = query.where(Competition.archived_at.is_(None))
    return sorted(
        {
            Season.for_date(
                value,
                start_month=settings.season_start_month,
                start_day=settings.season_start_day,
            )
            for value in db.scalars(query).all()
        },
        reverse=True,
    )


def result_archive_stats(results: list[Result]) -> dict[str, int]:
    return {
        "results": len(results),
        "members": len({result.member_id for result in results}),
        "competitions": len({result.competition_id for result in results}),
        "placed": sum(1 for result in results if result.place is not None),
    }


def apply_result_filters(
    query,
    *,
    selected_season: Season | None,
    selected_member_id: int | None,
    selected_competition_id: int | None,
    selected_category_id: int | None,
    selected_style_subcategory_id: int | None,
    selected_placement: str | None,
    search_query: str | None,
):
    needs_style_join = selected_category_id is not None or search_query is not None
    if needs_style_join:
        query = query.join(Result.style_subcategory)
    if search_query is not None:
        query = query.join(Result.member)

    if selected_season is not None:
        query = query.where(Competition.date >= selected_season.start_date).where(
            Competition.date < selected_season.end_boundary
        )
    if selected_member_id is not None:
        query = query.where(Result.member_id == selected_member_id)
    if selected_competition_id is not None:
        query = query.where(Result.competition_id == selected_competition_id)
    if selected_category_id is not None:
        query = query.where(StyleSubcategory.category_id == selected_category_id)
    if selected_style_subcategory_id is not None:
        query = query.where(Result.style_subcategory_id == selected_style_subcategory_id)
    if selected_placement == "placed":
        query = query.where(Result.place.is_not(None))
    elif selected_placement == "unplaced":
        query = query.where(Result.place.is_(None))
    if search_query is not None:
        search_pattern = f"%{search_query}%"
        query = query.where(
            or_(
                Member.display_name.ilike(search_pattern),
                Competition.name.ilike(search_pattern),
                StyleSubcategory.code.ilike(search_pattern),
                StyleSubcategory.name.ilike(search_pattern),
            )
        )
    return query


def validate_result(
    db: Session,
    *,
    member_id: int | None,
    competition_id: int | None,
    style_subcategory_id: int | None,
    bjcp_score: Decimal | None,
    place: int | None,
    placement_scope: PlacementScope | None,
    recipe_url: str | None,
    allow_inactive_member_id: int | None = None,
    allow_archived_competition_id: int | None = None,
) -> list[str]:
    errors = []

    member = db.get(Member, member_id) if member_id is not None else None
    inactive_member_is_allowed = (
        allow_inactive_member_id is not None
        and member_id == allow_inactive_member_id
    )
    if member_id is None:
        errors.append("Choose a member.")
    elif member is None or (
        member.deactivated_at is not None and not inactive_member_is_allowed
    ):
        errors.append("Choose an active member.")

    competition = db.get(Competition, competition_id) if competition_id is not None else None
    archived_competition_is_allowed = (
        allow_archived_competition_id is not None
        and competition_id == allow_archived_competition_id
    )
    if competition_id is None:
        errors.append("Choose a competition.")
    elif competition is None or (
        competition.archived_at is not None and not archived_competition_is_allowed
    ):
        errors.append("Choose a competition.")

    if style_subcategory_id is None:
        errors.append("Choose a BJCP style.")
    elif db.get(StyleSubcategory, style_subcategory_id) is None:
        errors.append("Choose a BJCP style.")

    if bjcp_score is not None and (bjcp_score <= 0 or bjcp_score > 50):
        errors.append("BJCP score must be greater than 0 and no more than 50.")

    if place is not None and place not in {1, 2, 3, 4}:
        errors.append("Place must be 1st, 2nd, 3rd, or HM.")

    if (place is None) != (placement_scope is None):
        errors.append("Place and placement scope must be set together.")

    _recipe_url, recipe_url_error = validate_link_url(recipe_url, field_label="Recipe URL")
    if recipe_url_error:
        errors.append(recipe_url_error)

    return errors


@dataclass(frozen=True)
class ResultImportRow:
    row_number: int
    member_id: int
    competition_id: int
    style_subcategory_id: int
    bjcp_score: Decimal | None
    place: int | None
    placement_scope: PlacementScope | None
    recipe_url: str | None
    recipe_file_url: str | None
    photo_url: str | None
    notes: str | None
    archived: bool


def parse_result_import(
    db: Session,
    content: bytes,
    *,
    create_missing_references: bool = False,
    resolution_counts: dict[str, int] | None = None,
) -> tuple[list[ResultImportRow], list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["CSV file must be UTF-8 text."]

    reader = csv.DictReader(StringIO(text))
    if reader.fieldnames is None:
        return [], ["CSV file must include a header row."]

    fieldnames = {field.strip() for field in reader.fieldnames if field}
    missing_fields = {
        "member_email",
        "competition_name",
        "competition_date",
        "style_subcategory_code",
    } - fieldnames
    unknown_fields = fieldnames - RESULT_IMPORT_COLUMNS
    errors = []
    if missing_fields:
        errors.append(f"Missing required columns: {', '.join(sorted(missing_fields))}.")
    if unknown_fields:
        errors.append(f"Unknown columns: {', '.join(sorted(unknown_fields))}.")
    if errors:
        return [], errors

    members_by_email = {
        member.email: member for member in db.scalars(select(Member).order_by(Member.email)).all()
    }
    competitions_by_key = {
        (competition.name, competition.date): competition
        for competition in db.scalars(select(Competition)).all()
    }
    subcategories = db.scalars(
        select(StyleSubcategory).options(selectinload(StyleSubcategory.category))
    ).all()

    rows = []
    for index, raw_row in enumerate(reader, start=2):
        row_errors = []
        member = resolve_import_member(
            db,
            raw_row,
            members_by_email,
            index,
            row_errors,
            create_missing_references=create_missing_references,
            resolution_counts=resolution_counts,
        )
        competition = resolve_import_competition(
            db,
            raw_row,
            competitions_by_key,
            index,
            row_errors,
            create_missing_references=create_missing_references,
            resolution_counts=resolution_counts,
        )
        style_subcategory = resolve_import_style(
            db,
            raw_row,
            subcategories,
            index,
            row_errors,
            create_missing_references=create_missing_references,
            resolution_counts=resolution_counts,
        )
        bjcp_score = parse_bjcp_score(raw_row.get("bjcp_score"), index, row_errors)
        place = parse_place(raw_row.get("place"), index, row_errors)
        placement_scope = parse_placement_scope(raw_row.get("placement_scope"), index, row_errors)
        validate_import_place_scope(place, placement_scope, index, row_errors)
        recipe_url = parse_optional_url(
            raw_row.get("recipe_url"),
            "recipe_url",
            index,
            row_errors,
        )
        recipe_file_url = parse_optional_url(
            raw_row.get("recipe_file_url"),
            "recipe_file_url",
            index,
            row_errors,
            allow_upload_path=True,
        )
        photo_url = parse_optional_url(
            raw_row.get("photo_url"),
            "photo_url",
            index,
            row_errors,
            allow_upload_path=True,
        )
        notes = parse_optional_text(raw_row.get("notes"), 2000, "notes", index, row_errors)
        archived = parse_result_archived(raw_row, index, row_errors)

        errors.extend(row_errors)
        if row_errors:
            continue
        if member is None or competition is None or style_subcategory is None:
            continue
        rows.append(
            ResultImportRow(
                row_number=index,
                member_id=member.id,
                competition_id=competition.id,
                style_subcategory_id=style_subcategory.id,
                bjcp_score=bjcp_score,
                place=place,
                placement_scope=placement_scope,
                recipe_url=recipe_url,
                recipe_file_url=recipe_file_url,
                photo_url=photo_url,
                notes=notes,
                archived=archived,
            )
        )

    if not rows and not errors:
        errors.append("CSV file must include at least one result row.")
    return ([] if errors else rows), errors


def analyze_result_import(
    db: Session,
    rows: list[ResultImportRow],
) -> dict[str, object]:
    member_ids = {row.member_id for row in rows}
    competition_ids = {row.competition_id for row in rows}
    style_ids = {row.style_subcategory_id for row in rows}
    members = {
        member.id: member
        for member in db.scalars(select(Member).where(Member.id.in_(member_ids))).all()
    }
    competitions = {
        competition.id: competition
        for competition in db.scalars(
            select(Competition).where(Competition.id.in_(competition_ids))
        ).all()
    }
    subcategories = {
        subcategory.id: subcategory
        for subcategory in db.scalars(
            select(StyleSubcategory)
            .where(StyleSubcategory.id.in_(style_ids))
            .options(selectinload(StyleSubcategory.category))
        ).all()
    }

    preview_rows = []
    creates = 0
    skips = 0
    warnings = []
    seen_keys: set[tuple[object, ...]] = set()
    for row in rows:
        key = result_import_key(row)
        duplicate_in_file = key in seen_keys
        duplicate_in_database = result_duplicate_exists(db, row)
        action = "skip" if duplicate_in_file or duplicate_in_database else "create"
        if action == "skip":
            skips += 1
            if duplicate_in_file:
                warnings.append(f"Row {row.row_number}: duplicate of an earlier CSV row.")
            else:
                warnings.append(f"Row {row.row_number}: likely duplicate of an existing result.")
        else:
            creates += 1
        seen_keys.add(key)

        member = members.get(row.member_id)
        competition = competitions.get(row.competition_id)
        subcategory = subcategories.get(row.style_subcategory_id)
        preview_rows.append(
            {
                "row": row.row_number,
                "action": action,
                "label": member.display_name if member else f"Member {row.member_id}",
                "detail": result_preview_detail(row, competition, subcategory),
            }
        )
    return {
        "total": len(rows),
        "creates": creates,
        "updates": 0,
        "skips": skips,
        "duplicates": skips,
        "warnings": warnings,
        "rows": preview_rows,
    }


def result_preview_detail(
    row: ResultImportRow,
    competition: Competition | None,
    subcategory: StyleSubcategory | None,
) -> str:
    competition_label = (
        f"{competition.date.isoformat()} {competition.name}" if competition else "Competition"
    )
    style_label = (
        f"{subcategory.code} {subcategory.name}"
        if subcategory
        else f"Style {row.style_subcategory_id}"
    )
    return f"{competition_label} / {style_label}"


def result_import_key(row: ResultImportRow) -> tuple[object, ...]:
    return (
        row.member_id,
        row.competition_id,
        row.style_subcategory_id,
        row.place,
        row.placement_scope,
        row.bjcp_score,
    )


def result_duplicate_exists(db: Session, row: ResultImportRow) -> bool:
    query = select(Result.id).where(
        Result.member_id == row.member_id,
        Result.competition_id == row.competition_id,
        Result.style_subcategory_id == row.style_subcategory_id,
    )
    query = query.where(Result.place.is_(None) if row.place is None else Result.place == row.place)
    query = query.where(
        Result.placement_scope.is_(None)
        if row.placement_scope is None
        else Result.placement_scope == row.placement_scope
    )
    query = query.where(
        Result.bjcp_score.is_(None)
        if row.bjcp_score is None
        else Result.bjcp_score == row.bjcp_score
    )
    return db.scalar(query.limit(1)) is not None


def preview_summary(noun: str, preview: dict[str, object]) -> str:
    return (
        f"Previewed {preview['total']} {noun}: "
        f"{preview['creates']} create, {preview['updates']} update, "
        f"{preview['skips']} skip."
    )


def resolve_import_member(
    db: Session,
    raw_row: dict[str, str | None],
    members_by_email: dict[str, Member],
    index: int,
    errors: list[str],
    *,
    create_missing_references: bool,
    resolution_counts: dict[str, int] | None,
) -> Member | None:
    member_email = (raw_row.get("member_email") or "").strip().lower()
    if not member_email:
        errors.append(f"Row {index}: member_email is required.")
        return None
    member = members_by_email.get(member_email)
    if member is None and create_missing_references:
        member = Member(
            email=member_email,
            display_name=member_display_name_from_row(raw_row, member_email),
        )
        db.add(member)
        db.flush()
        ensure_primary_email_alias(db, member)
        members_by_email[member.email] = member
        increment_resolution_count(resolution_counts, "members")
    elif member is None:
        errors.append(f"Row {index}: member_email {member_email} was not found.")
    return member


def resolve_import_competition(
    db: Session,
    raw_row: dict[str, str | None],
    competitions_by_key: dict[tuple[str, date], Competition],
    index: int,
    errors: list[str],
    *,
    create_missing_references: bool,
    resolution_counts: dict[str, int] | None,
) -> Competition | None:
    competition_name = (raw_row.get("competition_name") or "").strip()
    competition_date = parse_import_date(raw_row.get("competition_date"))
    if not competition_name:
        errors.append(f"Row {index}: competition_name is required.")
    if competition_date is None:
        errors.append(f"Row {index}: competition_date must be YYYY-MM-DD.")
    if not competition_name or competition_date is None:
        return None
    competition = competitions_by_key.get((competition_name, competition_date))
    if competition is None and create_missing_references:
        competition = Competition(
            name=competition_name,
            date=competition_date,
            competition_type=parse_import_competition_type(raw_row.get("competition_type")),
            url=None,
        )
        db.add(competition)
        db.flush()
        competitions_by_key[(competition.name, competition.date)] = competition
        increment_resolution_count(resolution_counts, "competitions")
    elif competition is None:
        errors.append(
            f"Row {index}: competition {competition_name} on "
            f"{competition_date.isoformat()} was not found."
        )
    return competition


def resolve_import_style(
    db: Session,
    raw_row: dict[str, str | None],
    subcategories: list[StyleSubcategory],
    index: int,
    errors: list[str],
    *,
    create_missing_references: bool,
    resolution_counts: dict[str, int] | None,
) -> StyleSubcategory | None:
    code = (raw_row.get("style_subcategory_code") or "").strip()
    raw_guide_year = (raw_row.get("style_guide_year") or "").strip()
    guide_year = parse_optional_int(raw_guide_year)
    if raw_guide_year and guide_year is None:
        errors.append(f"Row {index}: style_guide_year must be a year.")
    if not code:
        errors.append(f"Row {index}: style_subcategory_code is required.")
        return None

    matches = [
        subcategory
        for subcategory in subcategories
        if subcategory.code == code
        and (guide_year is None or subcategory.category.guide_year == guide_year)
    ]
    if not matches and create_missing_references:
        created = create_import_style(db, raw_row, guide_year, code, index, errors)
        if created is not None:
            subcategories.append(created)
            increment_resolution_count(resolution_counts, "styles")
            return created
    if not matches:
        qualifier = f" for {guide_year}" if guide_year is not None else ""
        errors.append(f"Row {index}: style_subcategory_code {code}{qualifier} was not found.")
        return None
    if len(matches) > 1:
        errors.append(
            f"Row {index}: style_subcategory_code {code} is ambiguous; add style_guide_year."
        )
        return None
    return matches[0]


def create_import_style(
    db: Session,
    raw_row: dict[str, str | None],
    guide_year: int | None,
    subcategory_code: str,
    index: int,
    errors: list[str],
) -> StyleSubcategory | None:
    category_code = (raw_row.get("style_category_code") or "").strip()
    category_name = (raw_row.get("style_category_name") or "").strip()
    subcategory_name = (raw_row.get("style_subcategory_name") or "").strip()
    if guide_year is None or not category_code or not category_name or not subcategory_name:
        errors.append(
            f"Row {index}: style {subcategory_code} cannot be created without "
            "style_guide_year, style_category_code, style_category_name, and "
            "style_subcategory_name."
        )
        return None

    category = db.scalar(
        select(StyleCategory).where(
            StyleCategory.guide_year == guide_year,
            StyleCategory.code == category_code,
        )
    )
    if category is None:
        category = StyleCategory(
            guide_year=guide_year,
            code=category_code,
            name=category_name,
        )
        db.add(category)
        db.flush()

    subcategory = StyleSubcategory(
        category=category,
        code=subcategory_code,
        name=subcategory_name,
    )
    db.add(subcategory)
    db.flush()
    return subcategory


def parse_bjcp_score(value: str | None, index: int, errors: list[str]) -> Decimal | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    try:
        score = Decimal(cleaned)
    except InvalidOperation:
        errors.append(f"Row {index}: bjcp_score must be a number.")
        return None
    if score <= 0 or score > 50:
        errors.append(f"Row {index}: bjcp_score must be greater than 0 and no more than 50.")
    return score


def parse_place(value: str | None, index: int, errors: list[str]) -> int | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    place = parse_place_value(cleaned)
    if place is None:
        errors.append(f"Row {index}: place must be 1, 2, 3, or HM.")
        return None
    if place not in {1, 2, 3, 4}:
        errors.append(f"Row {index}: place must be 1st, 2nd, 3rd, or HM.")
    return place


def parse_placement_scope(
    value: str | None,
    index: int,
    errors: list[str],
) -> PlacementScope | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    try:
        return PlacementScope(cleaned)
    except ValueError:
        errors.append(f"Row {index}: placement_scope must be category or best_of_show.")
        return None


def validate_import_place_scope(
    place: int | None,
    placement_scope: PlacementScope | None,
    index: int,
    errors: list[str],
) -> None:
    if (place is None) != (placement_scope is None):
        errors.append(f"Row {index}: place and placement_scope must be set together.")


def parse_optional_text(
    value: str | None,
    max_length: int,
    field_name: str,
    index: int,
    errors: list[str],
) -> str | None:
    cleaned = blank_to_none(value)
    if cleaned is not None and len(cleaned) > max_length:
        errors.append(f"Row {index}: {field_name} must be {max_length} characters or fewer.")
    return cleaned


def parse_optional_url(
    value: str | None,
    field_name: str,
    index: int,
    errors: list[str],
    *,
    allow_upload_path: bool = False,
) -> str | None:
    cleaned, error = validate_link_url(
        value,
        field_label=field_name,
        allow_upload_path=allow_upload_path,
    )
    if error:
        errors.append(f"Row {index}: {error}")
    return cleaned


def parse_result_archived(
    raw_row: dict[str, str | None],
    index: int,
    errors: list[str],
) -> bool:
    status = (raw_row.get("result_status") or "").strip().lower()
    if status:
        if status == "active":
            return False
        if status == "archived":
            return True
        errors.append(f"Row {index}: result_status must be active or archived.")
        return False
    return bool((raw_row.get("result_archived_at") or "").strip())


def parse_import_competition_type(value: str | None) -> CompetitionType:
    try:
        return CompetitionType((value or "").strip())
    except ValueError:
        return CompetitionType.OTHER


def member_display_name_from_row(raw_row: dict[str, str | None], email: str) -> str:
    display_name = (raw_row.get("member_display_name") or "").strip()
    if display_name:
        return display_name[:200]
    local_part = email.split("@", maxsplit=1)[0]
    words = local_part.replace(".", " ").replace("_", " ").replace("-", " ").split()
    return " ".join(word.capitalize() for word in words)[:200] if words else email[:200]


def increment_resolution_count(counts: dict[str, int] | None, key: str) -> None:
    if counts is not None:
        counts[key] = counts.get(key, 0) + 1


def parse_import_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def parse_optional_int(value: str | None) -> int | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def get_result_or_404(db: Session, result_id: int) -> Result:
    result = db.get(Result, result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return result


def load_result_detail_or_404(db: Session, result_id: int) -> Result:
    result = db.scalar(
        select(Result)
        .options(
            selectinload(Result.member),
            selectinload(Result.competition),
            selectinload(Result.style_subcategory).selectinload(StyleSubcategory.category),
        )
        .where(Result.id == result_id)
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return result


def result_form(result: Result) -> dict[str, str]:
    form = result_submission_form(
        member_id=result.member_id,
        competition_id=result.competition_id,
        style_subcategory_id=result.style_subcategory_id,
        bjcp_score=result.bjcp_score,
        place=result.place,
        placement_scope=result.placement_scope,
        recipe_url=result.recipe_url,
        notes=result.notes,
    )
    form["photo_url"] = result.photo_url or ""
    form["recipe_file_url"] = result.recipe_file_url or ""
    return form


def result_audit_metadata(result: Result) -> dict[str, object]:
    return {
        "member_id": result.member_id,
        "competition_id": result.competition_id,
        "style_subcategory_id": result.style_subcategory_id,
        "bjcp_score": str(result.bjcp_score) if result.bjcp_score is not None else None,
        "place": result.place,
        "placement_scope": result.placement_scope.value if result.placement_scope else None,
    }


def result_submission_form(
    *,
    member_id: int | None,
    competition_id: int | None,
    style_subcategory_id: int | None,
    bjcp_score: Decimal | None,
    place: int | None,
    placement_scope: PlacementScope | None,
    recipe_url: str | None,
    notes: str | None,
) -> dict[str, str]:
    return {
        "member_id": str(member_id) if member_id is not None else "",
        "competition_id": str(competition_id) if competition_id is not None else "",
        "style_subcategory_id": (
            str(style_subcategory_id) if style_subcategory_id is not None else ""
        ),
        "bjcp_score": str(bjcp_score) if bjcp_score is not None else "",
        "place": str(place) if place is not None else "",
        "placement_scope": placement_scope.value if placement_scope is not None else "",
        "recipe_url": recipe_url or "",
        "notes": notes or "",
    }


def save_result_attachments(
    result: Result,
    *,
    photo: UploadFile | None,
    recipe_file: UploadFile | None,
) -> list[str]:
    saved_urls = []
    try:
        if upload_has_file(photo):
            result.photo_url = save_result_upload(
                result_id=result.id,
                upload=photo,
                kind="photos",
            )
            saved_urls.append(result.photo_url)
        if upload_has_file(recipe_file):
            result.recipe_file_url = save_result_upload(
                result_id=result.id,
                upload=recipe_file,
                kind="recipes",
            )
            saved_urls.append(result.recipe_file_url)
    except ValueError as error:
        for url in saved_urls:
            delete_upload_url(url)
        return [str(error)]
    return []


def update_result_attachments(
    result: Result,
    *,
    photo: UploadFile | None,
    recipe_file: UploadFile | None,
    remove_photo: bool,
    remove_recipe_file: bool,
) -> list[str]:
    saved_urls = []
    new_photo_url = None
    new_recipe_file_url = None

    try:
        if upload_has_file(photo):
            new_photo_url = save_result_upload(
                result_id=result.id,
                upload=photo,
                kind="photos",
            )
            saved_urls.append(new_photo_url)
        if upload_has_file(recipe_file):
            new_recipe_file_url = save_result_upload(
                result_id=result.id,
                upload=recipe_file,
                kind="recipes",
            )
            saved_urls.append(new_recipe_file_url)
    except ValueError as error:
        for url in saved_urls:
            delete_upload_url(url)
        return [str(error)]

    old_photo_url = result.photo_url
    old_recipe_file_url = result.recipe_file_url

    if new_photo_url is not None:
        result.photo_url = new_photo_url
    elif remove_photo:
        result.photo_url = None

    if new_recipe_file_url is not None:
        result.recipe_file_url = new_recipe_file_url
    elif remove_recipe_file:
        result.recipe_file_url = None

    if old_photo_url and old_photo_url != result.photo_url:
        delete_upload_url(old_photo_url)
    if old_recipe_file_url and old_recipe_file_url != result.recipe_file_url:
        delete_upload_url(old_recipe_file_url)

    return []


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def csv_response(content: str, *, filename: str) -> Response:
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def isoformat_or_empty(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""
