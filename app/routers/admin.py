from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_admin
from app.db.models import (
    AppSetting,
    AuditLog,
    Competition,
    CompetitionType,
    Member,
    MemberEmail,
    MemberEmailKind,
    PlacementScope,
    Result,
    StyleCategory,
    StyleSubcategory,
)
from app.db.session import get_db
from app.services.audit import record_audit
from app.services.email import member_login_email_delivery_status
from app.services.leaderboard_settings import (
    leaderboard_settings_form,
    load_leaderboard_settings,
    save_leaderboard_settings,
    validate_leaderboard_settings_form,
)
from app.services.uploads import delete_upload_url
from app.services.urls import validate_link_url
from app.services.member_auth import ensure_primary_email_alias, member_with_any_email
from app.templating import templates

router = APIRouter(prefix="/admin")


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    _admin: Member = Depends(require_admin),
) -> HTMLResponse:
    metrics = dashboard_metrics(db)
    recent_results = db.scalars(
        select(Result)
        .join(Result.competition)
        .options(
            selectinload(Result.member),
            selectinload(Result.competition),
            selectinload(Result.style_subcategory).selectinload(StyleSubcategory.category),
        )
        .order_by(Result.created_at.desc())
        .limit(8)
    ).all()
    attention_items = [
        {
            "label": "Results without BJCP score",
            "count": scalar_count(
                db,
                select(func.count(Result.id)).where(Result.bjcp_score.is_(None)),
            ),
            "href": "/results",
        },
        {
            "label": "Results without attachments",
            "count": scalar_count(
                db,
                select(func.count(Result.id)).where(
                    Result.recipe_url.is_(None),
                    Result.recipe_file_url.is_(None),
                    Result.photo_url.is_(None),
                ),
            ),
            "href": "/results",
        },
        {
            "label": "Archived results",
            "count": scalar_count(
                db,
                select(func.count(Result.id)).where(Result.archived_at.is_not(None)),
            ),
            "href": "/results",
        },
        {
            "label": "Archived competitions",
            "count": scalar_count(
                db,
                select(func.count(Competition.id)).where(Competition.archived_at.is_not(None)),
            ),
            "href": "/competitions",
        },
    ]
    email_delivery = member_login_email_delivery_status()
    if not email_delivery["configured"]:
        attention_items.append(
            {
                "label": "Member login email delivery",
                "count": email_delivery["label"],
                "href": "/admin",
            }
        )
    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "metrics": metrics,
            "recent_results": recent_results,
            "attention_items": attention_items,
            "email_delivery": email_delivery,
        },
    )


@router.get("/data", response_class=HTMLResponse)
def data_tools(
    request: Request,
    db: Session = Depends(get_db),
    _admin: Member = Depends(require_admin),
) -> HTMLResponse:
    return render_data_tools(request, db)


@router.get("/audit", response_class=HTMLResponse)
def audit_log(
    request: Request,
    db: Session = Depends(get_db),
    _admin: Member = Depends(require_admin),
) -> HTMLResponse:
    entries = db.scalars(
        select(AuditLog)
        .options(selectinload(AuditLog.actor))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(200)
    ).all()
    return templates.TemplateResponse(
        request,
        "admin/audit.html",
        {"entries": entries},
    )


@router.get("/leaderboard", response_class=HTMLResponse)
def leaderboard_settings(
    request: Request,
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> HTMLResponse:
    settings = load_leaderboard_settings(db)
    return render_leaderboard_settings(request, settings=leaderboard_settings_form(settings))


@router.post("/leaderboard", response_class=HTMLResponse)
async def update_leaderboard_settings(
    request: Request,
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> HTMLResponse:
    form = {key: value for key, value in (await request.form()).items() if isinstance(value, str)}
    settings, errors = validate_leaderboard_settings_form(form)
    if errors:
        return render_leaderboard_settings(
            request,
            settings=form,
            errors=errors,
            status_code=400,
        )

    save_leaderboard_settings(db, settings)
    record_audit(
        db,
        actor=admin,
        action="update",
        entity_type="leaderboard_settings",
        entity_id=None,
        summary="Updated leaderboard settings.",
        metadata=form,
    )
    db.commit()
    return render_leaderboard_settings(
        request,
        settings=leaderboard_settings_form(settings),
        summary="Leaderboard settings saved.",
    )


@router.get("/data/backup.json")
def backup_json(
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> Response:
    record_audit(
        db,
        actor=admin,
        action="export",
        entity_type="backup",
        entity_id=None,
        summary="Downloaded JSON backup.",
    )
    db.commit()
    content = json.dumps(build_backup_payload(db), indent=2)
    return Response(
        content,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="trophy-case-backup.json"'},
    )


@router.post("/data/restore", response_class=HTMLResponse)
def restore_json(
    request: Request,
    backup_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> HTMLResponse:
    content = backup_file.file.read()
    backup_file.file.close()
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return render_data_tools(
            request,
            db,
            errors=["Backup file must be UTF-8 JSON."],
            status_code=400,
        )

    transaction = db.begin_nested()
    summary, errors = restore_backup_payload(db, payload)
    if errors:
        transaction.rollback()
        return render_data_tools(request, db, errors=errors, status_code=400)

    current_admin = db.get(Member, admin.id)
    if current_admin is not None:
        current_admin.is_admin = True
        current_admin.deactivated_at = None
    record_audit(
        db,
        actor=admin,
        action="restore",
        entity_type="backup",
        entity_id=None,
        summary=summary,
    )
    transaction.commit()
    db.commit()
    return render_data_tools(request, db, summary=summary)


@router.post("/data/clear-results", response_class=HTMLResponse)
def clear_results(
    request: Request,
    confirm_text: str = Form(""),
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> HTMLResponse:
    if confirm_text != "CLEAR RESULTS":
        return render_data_tools(
            request,
            db,
            errors=["Enter CLEAR RESULTS to remove result rows."],
            status_code=400,
        )

    result_uploads = db.execute(select(Result.photo_url, Result.recipe_file_url)).all()
    deleted_count = scalar_count(db, select(func.count(Result.id)))
    delete_result_uploads(result_uploads)
    db.execute(delete(Result))
    record_audit(
        db,
        actor=admin,
        action="clear",
        entity_type="results",
        entity_id=None,
        summary=f"Deleted {deleted_count} results.",
    )
    db.commit()
    return render_data_tools(request, db, summary=f"Deleted {deleted_count} results.")


@router.post("/data/clear-archive", response_class=HTMLResponse)
def clear_archive(
    request: Request,
    confirm_text: str = Form(""),
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> HTMLResponse:
    if confirm_text != "CLEAR ARCHIVE":
        return render_data_tools(
            request,
            db,
            errors=["Enter CLEAR ARCHIVE to remove archived records without live results."],
            status_code=400,
        )

    archived_result_ids = list(
        db.scalars(
            select(Result.id)
            .join(Result.competition)
            .where(or_(Result.archived_at.is_not(None), Competition.archived_at.is_not(None)))
        )
    )
    if archived_result_ids:
        result_uploads = db.execute(
            select(Result.photo_url, Result.recipe_file_url).where(
                Result.id.in_(archived_result_ids)
            )
        ).all()
        delete_result_uploads(result_uploads)
        db.execute(delete(Result).where(Result.id.in_(archived_result_ids)))

    deleted_competitions = 0
    competitions = db.scalars(
        select(Competition)
        .where(Competition.archived_at.is_not(None))
        .options(selectinload(Competition.results))
    ).all()
    for competition in competitions:
        if not competition.results:
            db.delete(competition)
            deleted_competitions += 1

    deleted_members = 0
    inactive_members = db.scalars(
        select(Member)
        .where(Member.deactivated_at.is_not(None))
        .where(Member.id != admin.id)
        .options(selectinload(Member.results))
    ).all()
    for member in inactive_members:
        if not member.results:
            db.delete(member)
            deleted_members += 1

    record_audit(
        db,
        actor=admin,
        action="clear",
        entity_type="archive",
        entity_id=None,
        summary=(
            f"Deleted {len(archived_result_ids)} archived results, "
            f"{deleted_competitions} archived competitions, and "
            f"{deleted_members} inactive members."
        ),
    )
    db.commit()
    return render_data_tools(
        request,
        db,
        summary=(
            f"Deleted {len(archived_result_ids)} archived results, "
            f"{deleted_competitions} archived competitions, and "
            f"{deleted_members} inactive members."
        ),
    )


def render_data_tools(
    request: Request,
    db: Session,
    *,
    summary: str | None = None,
    errors: list[str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    metrics = dashboard_metrics(db)
    return templates.TemplateResponse(
        request,
        "admin/data.html",
        {
            "metrics": metrics,
            "summary": summary,
            "errors": errors or [],
        },
        status_code=status_code,
    )


def render_leaderboard_settings(
    request: Request,
    *,
    settings: dict[str, str],
    summary: str | None = None,
    errors: list[str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/leaderboard.html",
        {
            "settings": settings,
            "summary": summary,
            "errors": errors or [],
            "competition_types": list(CompetitionType),
        },
        status_code=status_code,
    )


def dashboard_metrics(db: Session) -> dict[str, dict[str, int]]:
    result_total = scalar_count(db, select(func.count(Result.id)))
    active_results = scalar_count(
        db,
        select(func.count(Result.id))
        .join(Result.competition)
        .where(Result.archived_at.is_(None), Competition.archived_at.is_(None)),
    )
    competition_total = scalar_count(db, select(func.count(Competition.id)))
    active_competitions = scalar_count(
        db,
        select(func.count(Competition.id)).where(Competition.archived_at.is_(None)),
    )
    member_total = scalar_count(db, select(func.count(Member.id)))
    active_members = scalar_count(
        db,
        select(func.count(Member.id)).where(Member.deactivated_at.is_(None)),
    )
    style_categories = scalar_count(db, select(func.count(StyleCategory.id)))
    style_subcategories = scalar_count(db, select(func.count(StyleSubcategory.id)))
    return {
        "results": {
            "total": result_total,
            "active": active_results,
            "archived": result_total - active_results,
        },
        "competitions": {
            "total": competition_total,
            "active": active_competitions,
            "archived": competition_total - active_competitions,
        },
        "members": {
            "total": member_total,
            "active": active_members,
            "inactive": member_total - active_members,
        },
        "styles": {
            "categories": style_categories,
            "subcategories": style_subcategories,
        },
    }


def delete_result_uploads(result_uploads) -> None:
    for photo_url, recipe_file_url in result_uploads:
        delete_upload_url(photo_url)
        delete_upload_url(recipe_file_url)


def backup_email_for_kind(member: Member, kind: MemberEmailKind) -> str:
    for email in member.emails:
        if email.kind == kind:
            return email.email
    return ""


def sync_backup_member_email_aliases(
    db: Session,
    member: Member,
    *,
    paypal_email: str | None,
    mailing_list_email: str | None,
) -> None:
    ensure_primary_email_alias(db, member)
    normalized_primary = member.email.strip().lower()
    for member_email in list(member.emails):
        if member_email.kind != MemberEmailKind.PRIMARY and member_email.email == normalized_primary:
            db.delete(member_email)
    db.flush()
    desired = {
        MemberEmailKind.PAYPAL: backup_alias_email_or_none(paypal_email, member.email),
        MemberEmailKind.MAILING_LIST: backup_alias_email_or_none(
            mailing_list_email,
            member.email,
        ),
    }
    existing_by_kind = {email.kind: email for email in member.emails}
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


def backup_alias_email_or_none(value: str | None, primary_email: str) -> str | None:
    if value is None:
        return None
    email = value.strip().lower()
    if not email or email == primary_email.strip().lower():
        return None
    return email


def build_backup_payload(db: Session) -> dict[str, Any]:
    categories = db.scalars(
        select(StyleCategory).order_by(StyleCategory.guide_year, StyleCategory.code)
    ).all()
    subcategories = db.scalars(
        select(StyleSubcategory)
        .options(selectinload(StyleSubcategory.category))
        .order_by(StyleSubcategory.code, StyleSubcategory.name)
    ).all()
    members = db.scalars(
        select(Member).options(selectinload(Member.emails)).order_by(Member.email)
    ).all()
    competitions = db.scalars(
        select(Competition).order_by(Competition.date, Competition.name)
    ).all()
    results = db.scalars(
        select(Result)
        .options(
            selectinload(Result.member),
            selectinload(Result.competition),
            selectinload(Result.style_subcategory).selectinload(StyleSubcategory.category),
        )
        .order_by(Result.created_at, Result.id)
    ).all()
    app_settings = db.scalars(select(AppSetting).order_by(AppSetting.key)).all()
    audit_logs = db.scalars(
        select(AuditLog)
        .options(selectinload(AuditLog.actor))
        .order_by(AuditLog.created_at, AuditLog.id)
    ).all()
    return {
        "format": "trophy-case.backup.v1",
        "exported_at": datetime.now(UTC).isoformat(),
        "app_settings": [
            {
                "key": setting.key,
                "value": setting.value,
            }
            for setting in app_settings
        ],
        "style_categories": [
            {
                "guide_year": category.guide_year,
                "code": category.code,
                "name": category.name,
            }
            for category in categories
        ],
        "style_subcategories": [
            {
                "guide_year": subcategory.category.guide_year,
                "category_code": subcategory.category.code,
                "code": subcategory.code,
                "name": subcategory.name,
            }
            for subcategory in subcategories
        ],
        "members": [
            {
                "email": member.email,
                "paypal_email": backup_email_for_kind(member, MemberEmailKind.PAYPAL),
                "mailing_list_email": backup_email_for_kind(
                    member,
                    MemberEmailKind.MAILING_LIST,
                ),
                "display_name": member.display_name,
                "is_admin": member.is_admin,
                "good_standing": member.good_standing,
                "status": "inactive" if member.deactivated_at else "active",
            }
            for member in members
        ],
        "competitions": [
            {
                "name": competition.name,
                "date": competition.date.isoformat(),
                "competition_type": competition.competition_type.value,
                "url": competition.url,
                "status": "archived" if competition.archived_at else "active",
            }
            for competition in competitions
        ],
        "results": [
            {
                "member_email": result.member.email,
                "competition_name": result.competition.name,
                "competition_date": result.competition.date.isoformat(),
                "style_guide_year": result.style_subcategory.category.guide_year,
                "style_subcategory_code": result.style_subcategory.code,
                "bjcp_score": str(result.bjcp_score) if result.bjcp_score is not None else None,
                "place": result.place,
                "placement_scope": (
                    result.placement_scope.value if result.placement_scope is not None else None
                ),
                "recipe_url": result.recipe_url,
                "recipe_file_url": result.recipe_file_url,
                "photo_url": result.photo_url,
                "notes": result.notes,
                "status": "archived" if result.archived_at else "active",
            }
            for result in results
        ],
        "audit_logs": [
            {
                "created_at": audit_log.created_at.isoformat(),
                "actor_email": audit_log.actor.email if audit_log.actor else None,
                "action": audit_log.action,
                "entity_type": audit_log.entity_type,
                "entity_id": audit_log.entity_id,
                "summary": audit_log.summary,
                "metadata_json": audit_log.metadata_json,
            }
            for audit_log in audit_logs
        ],
    }


def restore_backup_payload(db: Session, payload: Any) -> tuple[str, list[str]]:
    if not isinstance(payload, dict) or payload.get("format") != "trophy-case.backup.v1":
        return "", ["Backup format is not supported."]

    errors: list[str] = []
    counts = {
        "settings": 0,
        "categories": 0,
        "subcategories": 0,
        "members": 0,
        "competitions": 0,
        "results": 0,
        "skipped_results": 0,
        "audit_logs": 0,
    }

    for index, item in enumerate(as_list(payload.get("app_settings")), start=1):
        if not isinstance(item, dict):
            errors.append(f"App setting {index}: row must be an object.")
            continue
        key = clean_text(item.get("key"))
        value = clean_text(item.get("value"))
        if not key or not key.startswith("leaderboard."):
            errors.append(f"App setting {index}: key must start with leaderboard.")
            continue
        setting = db.get(AppSetting, key)
        if setting is None:
            setting = AppSetting(key=key, value=value)
            db.add(setting)
        else:
            setting.value = value
        counts["settings"] += 1

    category_lookup: dict[tuple[int, str], StyleCategory] = {}
    for index, item in enumerate(as_list(payload.get("style_categories")), start=1):
        if not isinstance(item, dict):
            errors.append(f"Style category {index}: row must be an object.")
            continue
        guide_year = parse_int(item.get("guide_year"))
        code = clean_text(item.get("code"))
        name = clean_text(item.get("name"))
        if guide_year is None or not code or not name:
            errors.append(f"Style category {index}: guide_year, code, and name are required.")
            continue
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
        category_lookup[(guide_year, code)] = category
        counts["categories"] += 1

    db.flush()
    for index, item in enumerate(as_list(payload.get("style_subcategories")), start=1):
        if not isinstance(item, dict):
            errors.append(f"Style subcategory {index}: row must be an object.")
            continue
        guide_year = parse_int(item.get("guide_year"))
        category_code = clean_text(item.get("category_code"))
        code = clean_text(item.get("code"))
        name = clean_text(item.get("name"))
        category = category_lookup.get((guide_year or 0, category_code))
        if category is None and guide_year is not None and category_code:
            category = db.scalar(
                select(StyleCategory).where(
                    StyleCategory.guide_year == guide_year,
                    StyleCategory.code == category_code,
                )
            )
        if category is None or not code or not name:
            errors.append(
                f"Style subcategory {index}: guide_year, category_code, code, "
                "and name must resolve."
            )
            continue
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
        counts["subcategories"] += 1

    db.flush()
    for index, item in enumerate(as_list(payload.get("members")), start=1):
        if not isinstance(item, dict):
            errors.append(f"Member {index}: row must be an object.")
            continue
        email = clean_text(item.get("email")).lower()
        paypal_email = none_or_text(item.get("paypal_email"))
        mailing_list_email = none_or_text(item.get("mailing_list_email") or item.get("list_email"))
        display_name = clean_text(item.get("display_name"))
        status = clean_text(item.get("status") or "active").lower()
        if not email or "@" not in email or not display_name:
            errors.append(f"Member {index}: email and display_name are required.")
            continue
        if paypal_email is not None and "@" not in paypal_email:
            errors.append(f"Member {index}: paypal_email must look like an email address.")
            continue
        if mailing_list_email is not None and "@" not in mailing_list_email:
            errors.append(f"Member {index}: mailing_list_email must look like an email address.")
            continue
        if status not in {"active", "inactive"}:
            errors.append(f"Member {index}: status must be active or inactive.")
            continue
        member = member_with_any_email(
            db,
            [email, paypal_email or "", mailing_list_email or ""],
        )
        if member is None:
            member = Member(email=email, display_name=display_name)
            db.add(member)
            db.flush()
        else:
            member.email = email
        member.display_name = display_name
        member.is_admin = parse_bool(item.get("is_admin"))
        member.good_standing = (
            parse_bool(item.get("good_standing")) if "good_standing" in item else True
        )
        member.deactivated_at = datetime.now(UTC) if status == "inactive" else None
        sync_backup_member_email_aliases(
            db,
            member,
            paypal_email=paypal_email,
            mailing_list_email=mailing_list_email,
        )
        counts["members"] += 1

    db.flush()
    for index, item in enumerate(as_list(payload.get("competitions")), start=1):
        if not isinstance(item, dict):
            errors.append(f"Competition {index}: row must be an object.")
            continue
        name = clean_text(item.get("name"))
        parsed_date = parse_date(item.get("date"))
        competition_type = parse_competition_type(item.get("competition_type"))
        status = clean_text(item.get("status") or "active").lower()
        if not name or parsed_date is None or competition_type is None:
            errors.append(f"Competition {index}: name, date, and competition_type are required.")
            continue
        if status not in {"active", "archived"}:
            errors.append(f"Competition {index}: status must be active or archived.")
            continue
        competition_url, url_error = validate_link_url(item.get("url"), field_label="url")
        if url_error:
            errors.append(f"Competition {index}: {url_error}")
            continue
        competition = db.scalar(
            select(Competition).where(
                Competition.name == name,
                Competition.date == parsed_date,
            )
        )
        if competition is None:
            competition = Competition(
                name=name,
                date=parsed_date,
                competition_type=competition_type,
            )
            db.add(competition)
        competition.competition_type = competition_type
        competition.url = competition_url
        competition.archived_at = datetime.now(UTC) if status == "archived" else None
        counts["competitions"] += 1

    db.flush()
    seen_result_keys: set[tuple[Any, ...]] = set()
    for index, item in enumerate(as_list(payload.get("results")), start=1):
        if not isinstance(item, dict):
            errors.append(f"Result {index}: row must be an object.")
            continue
        result, result_errors = restore_result_from_payload(db, index, item)
        if result_errors:
            errors.extend(result_errors)
            continue
        assert result is not None
        key = result_identity_key(result)
        if key in seen_result_keys or result_exists(db, key):
            counts["skipped_results"] += 1
            continue
        seen_result_keys.add(key)
        db.add(result)
        counts["results"] += 1

    for index, item in enumerate(as_list(payload.get("audit_logs")), start=1):
        if not isinstance(item, dict):
            errors.append(f"Audit log {index}: row must be an object.")
            continue
        audit_log = restore_audit_log_from_payload(db, index, item, errors)
        if audit_log is not None:
            db.add(audit_log)
            counts["audit_logs"] += 1

    if errors:
        return "", errors
    summary = (
        "Restored "
        f"{counts['members']} members, {counts['competitions']} competitions, "
        f"{counts['categories']} categories, {counts['subcategories']} subcategories, "
        f"{counts['results']} results, {counts['settings']} settings, and "
        f"{counts['audit_logs']} audit entries."
    )
    if counts["skipped_results"]:
        summary += f" Skipped {counts['skipped_results']} duplicate results."
    return summary, []


def restore_result_from_payload(
    db: Session,
    index: int,
    item: dict[str, Any],
) -> tuple[Result | None, list[str]]:
    member_email = clean_text(item.get("member_email")).lower()
    competition_name = clean_text(item.get("competition_name"))
    competition_date = parse_date(item.get("competition_date"))
    style_guide_year = parse_int(item.get("style_guide_year"))
    style_code = clean_text(item.get("style_subcategory_code"))
    bjcp_score = parse_decimal(item.get("bjcp_score"))
    place = parse_int(item.get("place"))
    placement_scope = parse_placement_scope(item.get("placement_scope"))
    status = clean_text(item.get("status") or "active").lower()
    recipe_url, recipe_url_error = validate_link_url(
        item.get("recipe_url"),
        field_label="recipe_url",
    )
    recipe_file_url, recipe_file_url_error = validate_link_url(
        item.get("recipe_file_url"),
        field_label="recipe_file_url",
        allow_upload_path=True,
    )
    photo_url, photo_url_error = validate_link_url(
        item.get("photo_url"),
        field_label="photo_url",
        allow_upload_path=True,
    )
    errors = []

    member = db.scalar(select(Member).where(Member.email == member_email))
    if member is None:
        errors.append(f"Result {index}: member_email was not found.")
    competition = None
    if competition_date is not None:
        competition = db.scalar(
            select(Competition).where(
                Competition.name == competition_name,
                Competition.date == competition_date,
            )
        )
    if competition is None:
        errors.append(f"Result {index}: competition was not found.")
    subcategory = None
    if style_guide_year is not None and style_code:
        subcategory = db.scalar(
            select(StyleSubcategory)
            .join(StyleSubcategory.category)
            .where(
                StyleCategory.guide_year == style_guide_year,
                StyleSubcategory.code == style_code,
            )
        )
    if subcategory is None:
        errors.append(f"Result {index}: style_subcategory_code was not found.")
    if bjcp_score is None and item.get("bjcp_score") not in {None, ""}:
        errors.append(f"Result {index}: bjcp_score must be a decimal.")
    if bjcp_score is not None and (bjcp_score <= 0 or bjcp_score > 50):
        errors.append(f"Result {index}: bjcp_score must be greater than 0 and no more than 50.")
    if place is not None and place not in {1, 2, 3, 4}:
        errors.append(f"Result {index}: place must be between 1st and 4th.")
    if (place is None) != (placement_scope is None):
        errors.append(f"Result {index}: place and placement_scope must be set together.")
    if status not in {"active", "archived"}:
        errors.append(f"Result {index}: status must be active or archived.")
    for url_error in (recipe_url_error, recipe_file_url_error, photo_url_error):
        if url_error:
            errors.append(f"Result {index}: {url_error}")
    if errors:
        return None, errors

    assert member is not None
    assert competition is not None
    assert subcategory is not None
    return (
        Result(
            member_id=member.id,
            competition_id=competition.id,
            style_subcategory_id=subcategory.id,
            bjcp_score=bjcp_score,
            place=place,
            placement_scope=placement_scope,
            recipe_url=recipe_url,
            recipe_file_url=recipe_file_url,
            photo_url=photo_url,
            notes=none_or_text(item.get("notes")),
            archived_at=datetime.now(UTC) if status == "archived" else None,
        ),
        [],
    )


def restore_audit_log_from_payload(
    db: Session,
    index: int,
    item: dict[str, Any],
    errors: list[str],
) -> AuditLog | None:
    action = clean_text(item.get("action"))
    entity_type = clean_text(item.get("entity_type"))
    summary = clean_text(item.get("summary"))
    if not action or not entity_type or not summary:
        errors.append(f"Audit log {index}: action, entity_type, and summary are required.")
        return None

    actor = None
    actor_email = clean_text(item.get("actor_email")).lower()
    if actor_email:
        actor = db.scalar(select(Member).where(Member.email == actor_email))
    return AuditLog(
        created_at=parse_datetime(item.get("created_at")) or datetime.now(UTC),
        actor_member_id=actor.id if actor else None,
        action=action[:80],
        entity_type=entity_type[:80],
        entity_id=parse_int(item.get("entity_id")),
        summary=summary[:500],
        metadata_json=none_or_text(item.get("metadata_json")),
    )


def result_identity_key(result: Result) -> tuple[Any, ...]:
    return (
        result.member_id,
        result.competition_id,
        result.style_subcategory_id,
        result.place,
        result.placement_scope,
        result.bjcp_score,
    )


def result_exists(db: Session, key: tuple[Any, ...]) -> bool:
    member_id, competition_id, style_id, place, placement_scope, bjcp_score = key
    query = select(Result.id).where(
        Result.member_id == member_id,
        Result.competition_id == competition_id,
        Result.style_subcategory_id == style_id,
    )
    query = query.where(Result.place.is_(None) if place is None else Result.place == place)
    query = query.where(
        Result.placement_scope.is_(None)
        if placement_scope is None
        else Result.placement_scope == placement_scope
    )
    query = query.where(
        Result.bjcp_score.is_(None) if bjcp_score is None else Result.bjcp_score == bjcp_score
    )
    return db.scalar(query.limit(1)) is not None


def scalar_count(db: Session, statement) -> int:
    return int(db.scalar(statement) or 0)


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def none_or_text(value: Any) -> str | None:
    cleaned = clean_text(value)
    return cleaned or None


def parse_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def parse_decimal(value: Any) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return clean_text(value).lower() in {"true", "t", "1", "yes", "y"}


def parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(clean_text(value))
    except ValueError:
        return None


def parse_datetime(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(clean_text(value))
    except ValueError:
        return None


def parse_competition_type(value: Any) -> CompetitionType | None:
    try:
        return CompetitionType(clean_text(value))
    except ValueError:
        return None


def parse_placement_scope(value: Any) -> PlacementScope | None:
    cleaned = clean_text(value)
    if not cleaned:
        return None
    try:
        return PlacementScope(cleaned)
    except ValueError:
        return None
