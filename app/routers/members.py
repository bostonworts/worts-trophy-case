from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_admin
from app.db.models import (
    Competition,
    Member,
    MemberEmail,
    MemberEmailKind,
    Result,
    StyleSubcategory,
)
from app.db.session import get_db
from app.domain.scoring import leaderboard_points
from app.services.audit import record_audit
from app.services.google_sheets import GoogleSheetImportError, fetch_google_sheet_csv
from app.services.leaderboard_settings import load_leaderboard_settings
from app.services.member_auth import email_in_use_by_other_member, member_with_any_email
from app.templating import templates

router = APIRouter()

MEMBER_IMPORT_COLUMNS = {
    "id",
    "member",
    "name",
    "email",
    "paypal_email",
    "mailing_list_email",
    "email_list_email",
    "list_email",
    "display_name",
    "is_admin",
    "good_standing",
    "status",
    "deactivated_at",
    "created_at",
    "updated_at",
}


@router.get("/members", response_class=HTMLResponse)
def index(
    request: Request,
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> HTMLResponse:
    rows = db.execute(
        select(Member, func.count(Result.id))
        .outerjoin(Result)
        .options(selectinload(Member.emails))
        .group_by(Member.id)
        .order_by(Member.deactivated_at.is_not(None), Member.display_name)
    ).all()
    member_rows = [
        {"member": member, "result_count": result_count}
        for member, result_count in rows
    ]
    return templates.TemplateResponse(
        request,
        "members/index.html",
        {"member_rows": member_rows},
    )


@router.get("/members.csv")
def export_members(
    db: Session = Depends(get_db),
    _admin: Member = Depends(require_admin),
) -> Response:
    members = db.scalars(
        select(Member).options(selectinload(Member.emails)).order_by(Member.display_name)
    ).all()
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "email",
            "paypal_email",
            "mailing_list_email",
            "display_name",
            "is_admin",
            "good_standing",
            "status",
            "deactivated_at",
            "created_at",
            "updated_at",
        ],
    )
    writer.writeheader()
    for member in members:
        writer.writerow(
            {
                "id": member.id,
                "email": member.email,
                "paypal_email": email_for_kind(member, MemberEmailKind.PAYPAL),
                "mailing_list_email": email_for_kind(member, MemberEmailKind.MAILING_LIST),
                "display_name": member.display_name,
                "is_admin": "true" if member.is_admin else "false",
                "good_standing": "true" if member.good_standing else "false",
                "status": "inactive" if member.deactivated_at else "active",
                "deactivated_at": isoformat_or_empty(member.deactivated_at),
                "created_at": isoformat_or_empty(member.created_at),
                "updated_at": isoformat_or_empty(member.updated_at),
            }
        )
    return csv_response(output.getvalue(), filename="members.csv")


@router.get("/members/import", response_class=HTMLResponse)
def import_form(
    request: Request,
    _admin: Member = Depends(require_admin),
) -> HTMLResponse:
    return render_import(request)


@router.post("/members/import", response_class=HTMLResponse)
def import_members(
    request: Request,
    csv_file: UploadFile | None = File(None),
    google_sheet_url: str | None = Form(None),
    action: str = Form("import"),
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> HTMLResponse:
    source, source_errors = load_member_import_source(csv_file, google_sheet_url)
    if source_errors:
        return render_import(request, errors=source_errors, status_code=400)

    assert source is not None
    plan, errors = parse_member_import(source.content)
    if errors:
        return render_import(request, errors=errors, status_code=400)

    preview = analyze_member_import(db, plan)
    if action == "preview":
        return render_import(
            request,
            summary=f"{preview_summary('members', preview)} Source: {source.label}.",
            preview=preview,
        )

    created = preview["creates"]
    updated = preview["updates"]
    for row in plan:
        member = member_with_any_email(db, import_row_emails(row))
        if member is None:
            member = Member(
                email=row.email,
                display_name=row.display_name,
                is_admin=row.is_admin,
                good_standing=row.good_standing,
            )
            db.add(member)
            db.flush()
        else:
            member.email = row.email
            member.display_name = row.display_name
            member.is_admin = row.is_admin
            member.good_standing = row.good_standing

        sync_member_email_aliases(
            db,
            member,
            primary_email=row.email,
            paypal_email=row.paypal_email,
            mailing_list_email=row.mailing_list_email,
        )

        if row.status == "inactive" and member.deactivated_at is None:
            member.deactivated_at = datetime.now(UTC)
        elif row.status == "active":
            member.deactivated_at = None

    record_audit(
        db,
        actor=admin,
        action="import",
        entity_type="members",
        entity_id=None,
        summary=(
            f"Imported {len(plan)} members from {source.label}: "
            f"{created} created, {updated} updated."
        ),
    )
    db.commit()
    return render_import(
        request,
        summary=(
            f"Imported {len(plan)} members from {source.label}: "
            f"{created} created, {updated} updated."
        ),
    )


@router.get("/members/new", response_class=HTMLResponse)
def new(
    request: Request,
    _admin: Member = Depends(require_admin),
) -> HTMLResponse:
    return render_form(request)


@router.get("/members/{member_id}", response_class=HTMLResponse)
def show(member_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    member = get_member_or_404(db, member_id)
    current_member = request.state.current_member
    is_admin = current_member is not None and current_member.is_admin

    active_results = db.scalars(
        member_results_query(member.id)
        .where(Result.archived_at.is_(None))
        .where(Competition.archived_at.is_(None))
    ).all()
    archived_results = []
    if is_admin:
        archived_results = db.scalars(
            member_results_query(member.id).where(
                (Result.archived_at.is_not(None)) | (Competition.archived_at.is_not(None))
            )
        ).all()

    leaderboard_settings = load_leaderboard_settings(db)
    active_rows = result_rows(active_results, settings=leaderboard_settings)
    archived_rows = result_rows(archived_results, settings=leaderboard_settings)
    stats = result_stats(active_rows)

    return templates.TemplateResponse(
        request,
        "members/show.html",
        {
            "member": member,
            "active_rows": active_rows,
            "archived_rows": archived_rows,
            "stats": stats,
        },
    )


@router.get("/members/{member_id}/edit", response_class=HTMLResponse)
def edit(
    member_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _admin: Member = Depends(require_admin),
) -> HTMLResponse:
    member = get_member_or_404(db, member_id)
    return render_form(
        request,
        form=member_form(member),
        form_action=f"/members/{member.id}",
        page_title="Edit Member",
        page_heading="Edit member",
        submit_label="Save Changes",
    )


@router.post("/members")
def create(
    request: Request,
    display_name: str = Form(...),
    email: str = Form(...),
    paypal_email: str | None = Form(None),
    mailing_list_email: str | None = Form(None),
    is_admin: bool = Form(False),
    good_standing: bool = Form(False),
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> Response:
    normalized_email = normalize_email(email)
    normalized_paypal_email = normalize_optional_email(paypal_email)
    normalized_mailing_list_email = normalize_optional_email(mailing_list_email)
    form = member_submission_form(
        display_name=display_name,
        email=normalized_email,
        paypal_email=normalized_paypal_email,
        mailing_list_email=normalized_mailing_list_email,
        is_admin=is_admin,
        good_standing=good_standing,
    )
    errors = validate_member(
        db,
        display_name=display_name,
        email=normalized_email,
        paypal_email=normalized_paypal_email,
        mailing_list_email=normalized_mailing_list_email,
    )
    if errors:
        return render_form(request, form=form, errors=errors, status_code=400)

    member = Member(
        email=normalized_email,
        display_name=display_name.strip(),
        is_admin=is_admin,
        good_standing=good_standing,
    )
    db.add(member)
    db.flush()
    sync_member_email_aliases(
        db,
        member,
        primary_email=normalized_email,
        paypal_email=normalized_paypal_email,
        mailing_list_email=normalized_mailing_list_email,
    )
    record_audit(
        db,
        actor=admin,
        action="create",
        entity_type="member",
        entity_id=member.id,
        summary=f"Created member {member.display_name}.",
        metadata={
            "email": member.email,
            "is_admin": member.is_admin,
            "good_standing": member.good_standing,
        },
    )
    db.commit()
    return RedirectResponse("/members", status_code=303)


@router.post("/members/{member_id}")
def update(
    member_id: int,
    request: Request,
    display_name: str = Form(...),
    email: str = Form(...),
    paypal_email: str | None = Form(None),
    mailing_list_email: str | None = Form(None),
    is_admin: bool = Form(False),
    good_standing: bool = Form(False),
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> Response:
    member = get_member_or_404(db, member_id)
    normalized_email = normalize_email(email)
    normalized_paypal_email = normalize_optional_email(paypal_email)
    normalized_mailing_list_email = normalize_optional_email(mailing_list_email)
    form = member_submission_form(
        display_name=display_name,
        email=normalized_email,
        paypal_email=normalized_paypal_email,
        mailing_list_email=normalized_mailing_list_email,
        is_admin=is_admin,
        good_standing=good_standing,
    )
    errors = validate_member(
        db,
        display_name=display_name,
        email=normalized_email,
        paypal_email=normalized_paypal_email,
        mailing_list_email=normalized_mailing_list_email,
        exclude_id=member.id,
    )
    if errors:
        return render_form(
            request,
            form=form,
            errors=errors,
            form_action=f"/members/{member.id}",
            page_title="Edit Member",
            page_heading="Edit member",
            submit_label="Save Changes",
            status_code=400,
        )

    member.email = normalized_email
    member.display_name = display_name.strip()
    member.is_admin = is_admin
    member.good_standing = good_standing
    sync_member_email_aliases(
        db,
        member,
        primary_email=normalized_email,
        paypal_email=normalized_paypal_email,
        mailing_list_email=normalized_mailing_list_email,
    )
    record_audit(
        db,
        actor=admin,
        action="update",
        entity_type="member",
        entity_id=member.id,
        summary=f"Updated member {member.display_name}.",
        metadata={
            "email": member.email,
            "is_admin": member.is_admin,
            "good_standing": member.good_standing,
        },
    )
    db.commit()
    return RedirectResponse("/members", status_code=303)


@router.post("/members/{member_id}/deactivate")
def deactivate(
    member_id: int,
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> RedirectResponse:
    member = db.get(Member, member_id)
    if member is not None:
        member.deactivated_at = datetime.now(UTC)
        record_audit(
            db,
            actor=admin,
            action="deactivate",
            entity_type="member",
            entity_id=member.id,
            summary=f"Deactivated member {member.display_name}.",
        )
        db.commit()
    return RedirectResponse("/members", status_code=303)


@router.post("/members/{member_id}/reactivate")
def reactivate(
    member_id: int,
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> RedirectResponse:
    member = db.get(Member, member_id)
    if member is not None:
        member.deactivated_at = None
        record_audit(
            db,
            actor=admin,
            action="reactivate",
            entity_type="member",
            entity_id=member.id,
            summary=f"Reactivated member {member.display_name}.",
        )
        db.commit()
    return RedirectResponse("/members", status_code=303)


def render_form(
    request: Request,
    *,
    form: dict[str, str] | None = None,
    errors: list[str] | None = None,
    form_action: str = "/members",
    page_title: str = "Add Member",
    page_heading: str = "Add member",
    submit_label: str = "Save Member",
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "members/new.html",
        {
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
        "members/import.html",
        {
            "errors": errors or [],
            "summary": summary,
            "columns": sorted(MEMBER_IMPORT_COLUMNS),
            "preview": preview,
        },
        status_code=status_code,
    )


def validate_member(
    db: Session,
    *,
    display_name: str,
    email: str,
    paypal_email: str | None = None,
    mailing_list_email: str | None = None,
    exclude_id: int | None = None,
) -> list[str]:
    errors = []
    cleaned_display_name = display_name.strip()
    cleaned_email = normalize_email(email)
    alias_emails = [
        ("PayPal email", normalize_optional_email(paypal_email)),
        ("Mailing list email", normalize_optional_email(mailing_list_email)),
    ]

    if not cleaned_display_name:
        errors.append("Display name is required.")
    elif len(cleaned_display_name) > 200:
        errors.append("Display name must be 200 characters or fewer.")

    if not cleaned_email:
        errors.append("Email is required.")
    elif len(cleaned_email) > 320:
        errors.append("Email must be 320 characters or fewer.")
    elif "@" not in cleaned_email:
        errors.append("Email must look like an email address.")

    seen_emails = set()
    for label, value in [("Email", cleaned_email), *alias_emails]:
        if not value:
            continue
        if len(value) > 320 or "@" not in value:
            errors.append(f"{label} must look like an email address.")
            continue
        if value in seen_emails:
            errors.append(f"{label} duplicates another email on this member.")
        seen_emails.add(value)
        if email_in_use_by_other_member(db, value, exclude_member_id=exclude_id):
            errors.append(f"{label} is already used by another member.")

    return errors


@dataclass(frozen=True)
class MemberImportRow:
    row_number: int
    email: str
    paypal_email: str | None
    mailing_list_email: str | None
    display_name: str
    is_admin: bool
    good_standing: bool
    status: str


@dataclass(frozen=True)
class MemberImportSource:
    content: bytes
    label: str


def load_member_import_source(
    csv_file: UploadFile | None,
    google_sheet_url: str | None,
) -> tuple[MemberImportSource | None, list[str]]:
    sheet_url = (google_sheet_url or "").strip()
    has_file = csv_file is not None and bool(csv_file.filename)
    if has_file and sheet_url:
        close_upload_file(csv_file)
        return None, ["Choose either a CSV file or a Google Sheets URL, not both."]
    if not has_file and not sheet_url:
        close_upload_file(csv_file)
        return None, ["Choose a CSV file or enter a Google Sheets URL."]

    if sheet_url:
        close_upload_file(csv_file)
        try:
            return MemberImportSource(
                content=fetch_google_sheet_csv(sheet_url),
                label="Google Sheets",
            ), []
        except GoogleSheetImportError as exc:
            return None, [str(exc)]

    assert csv_file is not None
    try:
        return MemberImportSource(content=csv_file.file.read(), label="CSV"), []
    finally:
        close_upload_file(csv_file)


def close_upload_file(csv_file: UploadFile | None) -> None:
    if csv_file is not None:
        csv_file.file.close()


def parse_member_import(content: bytes) -> tuple[list[MemberImportRow], list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["CSV file must be UTF-8 text."]

    reader = csv.DictReader(StringIO(text))
    if reader.fieldnames is None:
        return [], ["CSV file must include a header row."]

    normalized_fieldnames = [normalize_column_name(field) for field in reader.fieldnames]
    reader.fieldnames = normalized_fieldnames
    duplicate_fields = sorted(
        {
            field
            for field in normalized_fieldnames
            if field and normalized_fieldnames.count(field) > 1
        }
    )
    fieldnames = {field for field in normalized_fieldnames if field}
    email_fields = {
        "email",
        "paypal_email",
        "mailing_list_email",
        "email_list_email",
        "list_email",
    }
    if not ({"display_name", "name"} & fieldnames):
        missing_fields = {"display_name or name"}
    else:
        missing_fields = set()
    unknown_fields = fieldnames - MEMBER_IMPORT_COLUMNS
    errors = []
    if missing_fields:
        errors.append(f"Missing required columns: {', '.join(sorted(missing_fields))}.")
    if not (fieldnames & email_fields):
        errors.append(
            "Missing required email column: email, paypal_email, mailing_list_email, "
            "email_list_email, or list_email."
        )
    if duplicate_fields:
        errors.append(f"Duplicate columns: {', '.join(duplicate_fields)}.")
    if unknown_fields:
        errors.append(f"Unknown columns: {', '.join(sorted(unknown_fields))}.")
    if errors:
        return [], errors

    rows = []
    seen_emails = set()
    has_good_standing = bool({"good_standing", "member"} & fieldnames)
    for index, raw_row in enumerate(reader, start=2):
        email = normalize_email(raw_row.get("email") or "")
        paypal_email = normalize_optional_email(raw_row.get("paypal_email"))
        mailing_list_email = normalize_optional_email(
            raw_row.get("mailing_list_email")
            or raw_row.get("email_list_email")
            or raw_row.get("list_email")
        )
        if not email:
            email = mailing_list_email or paypal_email or ""
        display_name = (raw_row.get("display_name") or raw_row.get("name") or "").strip()

        row_emails = [
            ("email", email),
            ("paypal_email", paypal_email),
            ("mailing_list_email", mailing_list_email),
        ]
        if not any(value for _, value in row_emails):
            errors.append(f"Row {index}: at least one member email is required.")
        row_seen_emails = set()
        for label, value in row_emails:
            if not value:
                continue
            if "@" not in value or len(value) > 320:
                errors.append(f"Row {index}: {label} must look like an email address.")
                continue
            elif value in row_seen_emails:
                continue
            elif value in seen_emails:
                errors.append(f"Row {index}: duplicate email {value}.")
            row_seen_emails.add(value)
            seen_emails.add(value)

        if not display_name:
            errors.append(f"Row {index}: display_name is required.")
        elif len(display_name) > 200:
            errors.append(f"Row {index}: display_name must be 200 characters or fewer.")

        is_admin = parse_bool(raw_row.get("is_admin"))
        if is_admin is None:
            errors.append(f"Row {index}: is_admin must be true or false.")
            is_admin = False

        good_standing = (
            parse_bool(raw_row.get("good_standing") or raw_row.get("member"))
            if has_good_standing
            else True
        )
        if good_standing is None:
            errors.append(f"Row {index}: good_standing must be true or false.")
            good_standing = False

        status = (raw_row.get("status") or "active").strip().lower()
        if status not in {"active", "inactive"}:
            errors.append(f"Row {index}: status must be active or inactive.")
            status = "active"

        rows.append(
            MemberImportRow(
                row_number=index,
                email=email,
                paypal_email=paypal_email,
                mailing_list_email=mailing_list_email,
                display_name=display_name,
                is_admin=is_admin,
                good_standing=good_standing,
                status=status,
            )
        )

    if not rows and not errors:
        errors.append("CSV file must include at least one member row.")
    return ([] if errors else rows), errors


def analyze_member_import(
    db: Session,
    rows: list[MemberImportRow],
) -> dict[str, object]:
    preview_rows = []
    creates = 0
    updates = 0
    for row in rows:
        existing = member_with_any_email(db, import_row_emails(row))
        action = "update" if existing is not None else "create"
        if action == "update":
            updates += 1
        else:
            creates += 1
        preview_rows.append(
            {
                "row": row.row_number,
                "action": action,
                "label": row.display_name,
                "detail": row.email,
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


def parse_bool(value: str | None) -> bool | None:
    cleaned = (value or "").strip().lower()
    if cleaned in {"", "false", "f", "0", "no", "n"}:
        return False
    if cleaned in {"true", "t", "1", "yes", "y"}:
        return True
    return None


def normalize_column_name(value: str | None) -> str:
    cleaned = (value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", cleaned).strip("_")


def get_member_or_404(db: Session, member_id: int) -> Member:
    member = db.get(Member, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


def member_results_query(member_id: int):
    return (
        select(Result)
        .join(Result.competition)
        .options(
            selectinload(Result.member),
            selectinload(Result.competition),
            selectinload(Result.style_subcategory).selectinload(StyleSubcategory.category),
        )
        .where(Result.member_id == member_id)
        .order_by(Competition.date.desc(), Result.created_at.desc())
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


def member_form(member: Member) -> dict[str, str]:
    return member_submission_form(
        display_name=member.display_name,
        email=member.email,
        paypal_email=email_for_kind(member, MemberEmailKind.PAYPAL),
        mailing_list_email=email_for_kind(member, MemberEmailKind.MAILING_LIST),
        is_admin=member.is_admin,
        good_standing=member.good_standing,
    )


def member_submission_form(
    *,
    display_name: str,
    email: str,
    paypal_email: str | None,
    mailing_list_email: str | None,
    is_admin: bool,
    good_standing: bool,
) -> dict[str, str]:
    return {
        "display_name": display_name.strip(),
        "email": normalize_email(email),
        "paypal_email": normalize_optional_email(paypal_email) or "",
        "mailing_list_email": normalize_optional_email(mailing_list_email) or "",
        "is_admin": "true" if is_admin else "",
        "good_standing": "true" if good_standing else "",
    }


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_optional_email(value: str | None) -> str | None:
    cleaned = normalize_email(value or "")
    return cleaned or None


def email_for_kind(member: Member, kind: MemberEmailKind) -> str:
    for member_email in member.emails:
        if member_email.kind == kind:
            return member_email.email
    return ""


def import_row_emails(row: MemberImportRow) -> list[str]:
    return [
        email
        for email in [row.email, row.paypal_email, row.mailing_list_email]
        if email
    ]


def sync_member_email_aliases(
    db: Session,
    member: Member,
    *,
    primary_email: str,
    paypal_email: str | None,
    mailing_list_email: str | None,
) -> None:
    normalized_primary = normalize_email(primary_email)
    for member_email in list(member.emails):
        if member_email.kind != MemberEmailKind.PRIMARY and member_email.email == normalized_primary:
            db.delete(member_email)
    db.flush()
    desired = {
        MemberEmailKind.PRIMARY: normalized_primary,
        MemberEmailKind.PAYPAL: alias_email_or_none(paypal_email, primary_email),
        MemberEmailKind.MAILING_LIST: alias_email_or_none(mailing_list_email, primary_email),
    }
    existing_by_kind = {member_email.kind: member_email for member_email in member.emails}
    for kind, email in desired.items():
        existing = existing_by_kind.get(kind)
        if email is None:
            if existing is not None:
                db.delete(existing)
            continue
        if existing is None:
            db.add(MemberEmail(member=member, kind=kind, email=email))
        else:
            existing.email = email


def alias_email_or_none(value: str | None, primary_email: str) -> str | None:
    email = normalize_optional_email(value)
    if email is None or email == normalize_email(primary_email):
        return None
    return email


def csv_response(content: str, *, filename: str) -> Response:
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def isoformat_or_empty(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""
