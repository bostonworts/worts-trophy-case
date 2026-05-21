from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from io import StringIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_admin, require_member
from app.db.models import Competition, CompetitionType, Member, Result, StyleSubcategory
from app.db.session import get_db
from app.domain.scoring import leaderboard_points
from app.services.audit import record_audit
from app.services.leaderboard_settings import load_leaderboard_settings
from app.services.urls import validate_link_url
from app.templating import templates

router = APIRouter()

COMPETITION_IMPORT_COLUMNS = {
    "id",
    "name",
    "date",
    "competition_type",
    "url",
    "status",
    "archived_at",
    "created_at",
    "updated_at",
}


@router.get("/competitions", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    current_member = request.state.current_member
    is_admin = current_member is not None and current_member.is_admin
    active_competitions = db.scalars(
        select(Competition)
        .where(Competition.archived_at.is_(None))
        .order_by(Competition.date.desc())
    ).all()
    archived_competitions = []
    if is_admin:
        archived_competitions = db.scalars(
            select(Competition)
            .where(Competition.archived_at.is_not(None))
            .order_by(Competition.date.desc())
        ).all()
    return templates.TemplateResponse(
        request,
        "competitions/index.html",
        {
            "active_competitions": active_competitions,
            "archived_competitions": archived_competitions,
        },
    )


@router.get("/competitions.csv")
def export_competitions(
    db: Session = Depends(get_db),
    _admin: Member = Depends(require_admin),
) -> Response:
    competitions = db.scalars(select(Competition).order_by(Competition.date.desc())).all()
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "name",
            "date",
            "competition_type",
            "url",
            "status",
            "archived_at",
            "created_at",
            "updated_at",
        ],
    )
    writer.writeheader()
    for competition in competitions:
        writer.writerow(
            {
                "id": competition.id,
                "name": competition.name,
                "date": competition.date.isoformat(),
                "competition_type": competition.competition_type.value,
                "url": competition.url or "",
                "status": "archived" if competition.archived_at else "active",
                "archived_at": isoformat_or_empty(competition.archived_at),
                "created_at": isoformat_or_empty(competition.created_at),
                "updated_at": isoformat_or_empty(competition.updated_at),
            }
        )
    return csv_response(output.getvalue(), filename="competitions.csv")


@router.get("/competitions/import", response_class=HTMLResponse)
def import_form(
    request: Request,
    _admin: Member = Depends(require_admin),
) -> HTMLResponse:
    return render_import(request)


@router.post("/competitions/import", response_class=HTMLResponse)
def import_competitions(
    request: Request,
    csv_file: UploadFile = File(...),
    action: str = Form("import"),
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> HTMLResponse:
    content = csv_file.file.read()
    csv_file.file.close()
    plan, errors = parse_competition_import(content)
    if errors:
        return render_import(request, errors=errors, status_code=400)

    preview = analyze_competition_import(db, plan)
    if action == "preview":
        return render_import(
            request,
            summary=preview_summary("competitions", preview),
            preview=preview,
        )

    created = preview["creates"]
    updated = preview["updates"]
    for row in plan:
        competition = db.scalar(
            select(Competition).where(
                Competition.name == row.name,
                Competition.date == row.date,
            )
        )
        if competition is None:
            competition = Competition(
                name=row.name,
                date=row.date,
                competition_type=row.competition_type,
                url=row.url,
            )
            db.add(competition)
        else:
            competition.competition_type = row.competition_type
            competition.url = row.url

        if row.status == "archived" and competition.archived_at is None:
            competition.archived_at = datetime.now(UTC)
        elif row.status == "active":
            competition.archived_at = None

    record_audit(
        db,
        actor=admin,
        action="import",
        entity_type="competitions",
        entity_id=None,
        summary=(
            f"Imported {len(plan)} competitions: "
            f"{created} created, {updated} updated."
        ),
    )
    db.commit()
    return render_import(
        request,
        summary=f"Imported {len(plan)} competitions: {created} created, {updated} updated.",
    )


@router.get("/competitions/new", response_class=HTMLResponse)
def new(
    request: Request,
    member: Member = Depends(require_member),
) -> HTMLResponse:
    ensure_member_can_create_competition(member)
    return render_form(request)


@router.get("/competitions/{competition_id}", response_class=HTMLResponse)
def show(
    competition_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    competition = get_competition_or_404(db, competition_id)
    current_member = request.state.current_member
    is_admin = current_member is not None and current_member.is_admin
    if competition.archived_at is not None and not is_admin:
        raise HTTPException(status_code=404, detail="Competition not found")

    active_results = []
    if competition.archived_at is None:
        active_results = db.scalars(
            competition_results_query(competition.id).where(Result.archived_at.is_(None))
        ).all()

    archived_results = []
    if is_admin:
        archived_results = db.scalars(
            competition_results_query(competition.id).where(
                (Result.archived_at.is_not(None)) | (Competition.archived_at.is_not(None))
            )
        ).all()

    leaderboard_settings = load_leaderboard_settings(db)
    active_rows = result_rows(active_results, settings=leaderboard_settings)
    archived_rows = result_rows(archived_results, settings=leaderboard_settings)
    stats = result_stats(active_rows)

    return templates.TemplateResponse(
        request,
        "competitions/show.html",
        {
            "competition": competition,
            "active_rows": active_rows,
            "archived_rows": archived_rows,
            "stats": stats,
        },
    )


@router.get("/competitions/{competition_id}/edit", response_class=HTMLResponse)
def edit(
    competition_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _admin: Member = Depends(require_admin),
) -> HTMLResponse:
    competition = get_competition_or_404(db, competition_id)
    return render_form(
        request,
        form=competition_form(competition),
        form_action=f"/competitions/{competition.id}",
        page_title="Edit Competition",
        page_heading="Edit competition",
        submit_label="Save Changes",
    )


@router.post("/competitions")
def create(
    request: Request,
    name: str = Form(...),
    date_: date = Form(..., alias="date"),
    competition_type: CompetitionType = Form(...),
    url: str | None = Form(None),
    db: Session = Depends(get_db),
    member: Member = Depends(require_member),
) -> Response:
    ensure_member_can_create_competition(member)
    form = {
        "name": name,
        "date": date_.isoformat(),
        "competition_type": competition_type.value,
        "url": url or "",
    }
    errors = validate_competition(
        db,
        name=name,
        date_=date_,
        url=url,
    )
    if errors:
        return render_form(request, form=form, errors=errors, status_code=400)

    competition = Competition(
        name=name.strip(),
        date=date_,
        competition_type=competition_type,
        url=blank_to_none(url),
    )
    db.add(competition)
    db.flush()
    record_audit(
        db,
        actor=member,
        action="create",
        entity_type="competition",
        entity_id=competition.id,
        summary=f"Created competition {competition.name}.",
        metadata=competition_audit_metadata(competition),
    )
    db.commit()
    return RedirectResponse("/competitions", status_code=303)


def ensure_member_can_create_competition(member: Member) -> None:
    if member.is_admin or member.good_standing:
        return
    raise HTTPException(
        status_code=403,
        detail="Only active members in good standing can add competitions.",
    )


@router.post("/competitions/{competition_id}")
def update(
    competition_id: int,
    request: Request,
    name: str = Form(...),
    date_: date = Form(..., alias="date"),
    competition_type: CompetitionType = Form(...),
    url: str | None = Form(None),
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> Response:
    competition = get_competition_or_404(db, competition_id)
    form = {
        "name": name,
        "date": date_.isoformat(),
        "competition_type": competition_type.value,
        "url": url or "",
    }
    errors = validate_competition(
        db,
        name=name,
        date_=date_,
        url=url,
        exclude_id=competition.id,
    )
    if errors:
        return render_form(
            request,
            form=form,
            errors=errors,
            form_action=f"/competitions/{competition.id}",
            page_title="Edit Competition",
            page_heading="Edit competition",
            submit_label="Save Changes",
            status_code=400,
        )

    competition.name = name.strip()
    competition.date = date_
    competition.competition_type = competition_type
    competition.url = blank_to_none(url)
    record_audit(
        db,
        actor=admin,
        action="update",
        entity_type="competition",
        entity_id=competition.id,
        summary=f"Updated competition {competition.name}.",
        metadata=competition_audit_metadata(competition),
    )
    db.commit()
    return RedirectResponse("/competitions", status_code=303)


@router.post("/competitions/{competition_id}/archive")
def archive(
    competition_id: int,
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> RedirectResponse:
    competition = get_competition_or_404(db, competition_id)
    competition.archived_at = datetime.now(UTC)
    record_audit(
        db,
        actor=admin,
        action="archive",
        entity_type="competition",
        entity_id=competition.id,
        summary=f"Archived competition {competition.name}.",
    )
    db.commit()
    return RedirectResponse("/competitions", status_code=303)


@router.post("/competitions/{competition_id}/restore")
def restore(
    competition_id: int,
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> RedirectResponse:
    competition = get_competition_or_404(db, competition_id)
    competition.archived_at = None
    record_audit(
        db,
        actor=admin,
        action="restore",
        entity_type="competition",
        entity_id=competition.id,
        summary=f"Restored competition {competition.name}.",
    )
    db.commit()
    return RedirectResponse("/competitions", status_code=303)


def render_form(
    request: Request,
    *,
    form: dict[str, str] | None = None,
    errors: list[str] | None = None,
    form_action: str = "/competitions",
    page_title: str = "Add Competition",
    page_heading: str = "Add competition",
    submit_label: str = "Save Competition",
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "competitions/new.html",
        {
            "competition_types": list(CompetitionType),
            "form": form or {},
            "errors": errors or [],
            "form_action": form_action,
            "page_title": page_title,
            "page_heading": page_heading,
            "submit_label": submit_label,
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
        "competitions/import.html",
        {
            "errors": errors or [],
            "summary": summary,
            "columns": sorted(COMPETITION_IMPORT_COLUMNS),
            "competition_types": [competition_type.value for competition_type in CompetitionType],
            "preview": preview,
        },
        status_code=status_code,
    )


def validate_competition(
    db: Session,
    *,
    name: str,
    date_: date,
    url: str | None,
    exclude_id: int | None = None,
) -> list[str]:
    errors = []
    cleaned_name = name.strip()
    cleaned_url = blank_to_none(url)

    if not cleaned_name:
        errors.append("Competition name is required.")
    elif len(cleaned_name) > 240:
        errors.append("Competition name must be 240 characters or fewer.")

    _url, url_error = validate_link_url(cleaned_url, field_label="Competition URL")
    if url_error:
        errors.append(url_error)

    if cleaned_name:
        statement = select(Competition).where(
            Competition.name == cleaned_name,
            Competition.date == date_,
        )
        if exclude_id is not None:
            statement = statement.where(Competition.id != exclude_id)
        existing = db.scalar(statement)
        if existing is not None:
            errors.append("A competition with that name and date already exists.")

    return errors


@dataclass(frozen=True)
class CompetitionImportRow:
    row_number: int
    name: str
    date: date
    competition_type: CompetitionType
    url: str | None
    status: str


def parse_competition_import(content: bytes) -> tuple[list[CompetitionImportRow], list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["CSV file must be UTF-8 text."]

    reader = csv.DictReader(StringIO(text))
    if reader.fieldnames is None:
        return [], ["CSV file must include a header row."]

    fieldnames = {field.strip() for field in reader.fieldnames if field}
    missing_fields = {"name", "date", "competition_type"} - fieldnames
    unknown_fields = fieldnames - COMPETITION_IMPORT_COLUMNS
    errors = []
    if missing_fields:
        errors.append(f"Missing required columns: {', '.join(sorted(missing_fields))}.")
    if unknown_fields:
        errors.append(f"Unknown columns: {', '.join(sorted(unknown_fields))}.")
    if errors:
        return [], errors

    rows = []
    seen_keys = set()
    for index, raw_row in enumerate(reader, start=2):
        name = (raw_row.get("name") or "").strip()
        parsed_date = parse_date(raw_row.get("date"))
        competition_type = parse_competition_type(raw_row.get("competition_type"))
        url, url_error = validate_link_url(raw_row.get("url"), field_label="url")
        status = (raw_row.get("status") or "active").strip().lower()

        if not name:
            errors.append(f"Row {index}: name is required.")
        elif len(name) > 240:
            errors.append(f"Row {index}: name must be 240 characters or fewer.")
        if parsed_date is None:
            errors.append(f"Row {index}: date must be YYYY-MM-DD.")
            parsed_date = date.min
        if competition_type is None:
            errors.append(f"Row {index}: competition_type is invalid.")
            competition_type = CompetitionType.OTHER
        if url_error:
            errors.append(f"Row {index}: {url_error}")
        if status not in {"active", "archived"}:
            errors.append(f"Row {index}: status must be active or archived.")
            status = "active"

        key = (name, parsed_date)
        if name and parsed_date != date.min:
            if key in seen_keys:
                errors.append(f"Row {index}: duplicate competition name/date.")
            seen_keys.add(key)

        rows.append(
            CompetitionImportRow(
                row_number=index,
                name=name,
                date=parsed_date,
                competition_type=competition_type,
                url=url,
                status=status,
            )
        )

    if not rows and not errors:
        errors.append("CSV file must include at least one competition row.")
    return ([] if errors else rows), errors


def analyze_competition_import(
    db: Session,
    rows: list[CompetitionImportRow],
) -> dict[str, object]:
    preview_rows = []
    creates = 0
    updates = 0
    for row in rows:
        existing = db.scalar(
            select(Competition.id).where(
                Competition.name == row.name,
                Competition.date == row.date,
            )
        )
        action = "update" if existing is not None else "create"
        if action == "update":
            updates += 1
        else:
            creates += 1
        preview_rows.append(
            {
                "row": row.row_number,
                "action": action,
                "label": row.name,
                "detail": row.date.isoformat(),
            }
        )
    return {
        "total": len(rows),
        "creates": creates,
        "updates": updates,
        "skips": 0,
        "duplicates": updates,
        "warnings": [],
        "rows": preview_rows,
    }


def preview_summary(noun: str, preview: dict[str, object]) -> str:
    return (
        f"Previewed {preview['total']} {noun}: "
        f"{preview['creates']} create, {preview['updates']} update, "
        f"{preview['skips']} skip."
    )


def parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def parse_competition_type(value: str | None) -> CompetitionType | None:
    try:
        return CompetitionType((value or "").strip())
    except ValueError:
        return None


def get_competition_or_404(db: Session, competition_id: int) -> Competition:
    competition = db.get(Competition, competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="Competition not found")
    return competition


def competition_results_query(competition_id: int):
    return (
        select(Result)
        .join(Result.competition)
        .options(
            selectinload(Result.member),
            selectinload(Result.competition),
            selectinload(Result.style_subcategory).selectinload(StyleSubcategory.category),
        )
        .where(Result.competition_id == competition_id)
        .order_by(Result.place.is_(None), Result.place, Result.created_at.desc())
    )


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


def competition_form(competition: Competition) -> dict[str, str]:
    return {
        "name": competition.name,
        "date": competition.date.isoformat(),
        "competition_type": competition.competition_type.value,
        "url": competition.url or "",
    }


def competition_audit_metadata(competition: Competition) -> dict[str, str]:
    return {
        "name": competition.name,
        "date": competition.date.isoformat(),
        "competition_type": competition.competition_type.value,
        "url": competition.url or "",
    }


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
