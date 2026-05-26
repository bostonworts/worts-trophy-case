from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_admin, require_member
from app.db.models import (
    Member,
    MemberResultSubmission,
    MemberResultSubmissionStatus,
    PlacementScope,
    Result,
    StyleSubcategory,
)
from app.db.session import get_db
from app.routers.results import (
    blank_to_none,
    render_form,
    result_audit_metadata,
    result_submission_form,
    validate_result,
)
from app.services.audit import record_audit
from app.services.uploads import (
    copy_upload_url_to_result,
    delete_upload_url,
    save_submission_upload,
    upload_has_file,
)
from app.templating import templates

router = APIRouter()


@router.get("/me/results/new", response_class=HTMLResponse)
def new_member_result_submission(
    request: Request,
    db: Session = Depends(get_db),
    member: Member = Depends(require_member),
) -> HTMLResponse:
    ensure_member_can_submit(member)
    return render_form(
        request,
        db,
        form=result_submission_form(
            member_id=member.id,
            competition_id=None,
            style_subcategory_id=None,
            bjcp_score=None,
            place=None,
            placement_scope=None,
            recipe_url=None,
            notes=None,
        ),
        form_action="/me/results",
        page_title="Submit Result",
        page_heading="Submit result",
        submit_label=(
            "Submit for Review" if member.submission_review_required else "Submit Result"
        ),
        member_locked=member,
    )


@router.post("/me/results")
def create_member_result_submission(
    request: Request,
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
    member: Member = Depends(require_member),
) -> Response:
    ensure_member_can_submit(member)
    form = result_submission_form(
        member_id=member.id,
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
        member_id=member.id,
        competition_id=competition_id,
        style_subcategory_id=style_subcategory_id,
        bjcp_score=bjcp_score,
        place=place,
        placement_scope=placement_scope,
        recipe_url=recipe_url,
    )
    if errors:
        return render_form(
            request,
            db,
            form=form,
            errors=errors,
            form_action="/me/results",
            page_title="Submit Result",
            page_heading="Submit result",
            submit_label=(
                "Submit for Review" if member.submission_review_required else "Submit Result"
            ),
            member_locked=member,
            status_code=400,
        )

    assert competition_id is not None
    assert style_subcategory_id is not None
    submission = MemberResultSubmission(
        member_id=member.id,
        competition_id=competition_id,
        style_subcategory_id=style_subcategory_id,
        bjcp_score=bjcp_score,
        place=place,
        placement_scope=placement_scope,
        recipe_url=blank_to_none(recipe_url),
        notes=blank_to_none(notes),
    )
    db.add(submission)
    db.flush()
    attachment_errors = save_submission_attachments(
        submission,
        photo=photo,
        recipe_file=recipe_file,
    )
    if attachment_errors:
        db.rollback()
        return render_form(
            request,
            db,
            form=form,
            errors=attachment_errors,
            form_action="/me/results",
            page_title="Submit Result",
            page_heading="Submit result",
            submit_label=(
                "Submit for Review" if member.submission_review_required else "Submit Result"
            ),
            member_locked=member,
            status_code=400,
        )

    if not member.submission_review_required:
        result, publish_errors = approve_submission_with_result(
            db,
            submission,
            reviewer=None,
        )
        if publish_errors:
            db.rollback()
            return render_form(
                request,
                db,
                form=form,
                errors=publish_errors,
                form_action="/me/results",
                page_title="Submit Result",
                page_heading="Submit result",
                submit_label="Submit Result",
                member_locked=member,
                status_code=400,
            )
        assert result is not None
        record_audit(
            db,
            actor=member,
            action="submit",
            entity_type="member_result_submission",
            entity_id=submission.id,
            summary="Submitted trusted result.",
            metadata=submission_audit_metadata(submission),
        )
        record_audit(
            db,
            actor=member,
            action="create",
            entity_type="result",
            entity_id=result.id,
            summary="Created result from trusted member submission.",
            metadata=result_audit_metadata(result),
        )
        db.commit()
        return RedirectResponse(f"/results/{result.id}", status_code=303)

    record_audit(
        db,
        actor=member,
        action="submit",
        entity_type="member_result_submission",
        entity_id=submission.id,
        summary="Submitted result for review.",
        metadata=submission_audit_metadata(submission),
    )
    db.commit()
    return RedirectResponse(f"/me/submissions/{submission.id}", status_code=303)


@router.get("/me/submissions", response_class=HTMLResponse)
def my_result_submissions(
    request: Request,
    db: Session = Depends(get_db),
    member: Member = Depends(require_member),
) -> HTMLResponse:
    submissions = db.scalars(
        submission_select()
        .where(MemberResultSubmission.member_id == member.id)
        .order_by(MemberResultSubmission.created_at.desc(), MemberResultSubmission.id.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "submissions/index.html",
        {
            "submissions": submissions,
            "member": member,
        },
    )


@router.get("/me/submissions/{submission_id}", response_class=HTMLResponse)
def my_result_submission_detail(
    submission_id: int,
    request: Request,
    db: Session = Depends(get_db),
    member: Member = Depends(require_member),
) -> HTMLResponse:
    submission = get_submission_or_404(db, submission_id)
    if submission.member_id != member.id and not member.is_admin:
        raise HTTPException(status_code=404, detail="Submission not found")
    return render_submission_detail(request, submission=submission)


@router.get("/admin/submissions", response_class=HTMLResponse)
def admin_result_submissions(
    request: Request,
    db: Session = Depends(get_db),
    _admin: Member = Depends(require_admin),
) -> HTMLResponse:
    return render_admin_submissions(request, db)


@router.post("/admin/submissions/approve-all", response_class=HTMLResponse)
def approve_all_result_submissions(
    request: Request,
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> HTMLResponse:
    pending_ids = list(
        db.scalars(
            select(MemberResultSubmission.id)
            .where(MemberResultSubmission.status == MemberResultSubmissionStatus.PENDING)
            .order_by(MemberResultSubmission.created_at.asc(), MemberResultSubmission.id.asc())
        )
    )
    approved_count = 0
    errors = []
    for submission_id in pending_ids:
        submission = get_submission_or_404(db, submission_id, for_update=True)
        result, submission_errors = approve_pending_submission(db, submission, admin)
        if submission_errors:
            db.rollback()
            errors.append(
                f"Submission {submission_id}: {' '.join(submission_errors)}"
            )
            continue
        assert result is not None
        record_submission_approval_audit(db, submission=submission, result=result, admin=admin)
        db.commit()
        approved_count += 1

    summary = f"Approved {approved_count} pending submissions."
    return render_admin_submissions(
        request,
        db,
        summary=summary,
        errors=errors,
        status_code=400 if errors else 200,
    )


def render_admin_submissions(
    request: Request,
    db: Session,
    *,
    summary: str | None = None,
    errors: list[str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    pending_submissions = db.scalars(
        submission_select()
        .where(MemberResultSubmission.status == MemberResultSubmissionStatus.PENDING)
        .order_by(MemberResultSubmission.created_at.asc(), MemberResultSubmission.id.asc())
    ).all()
    reviewed_submissions = db.scalars(
        submission_select()
        .where(MemberResultSubmission.status != MemberResultSubmissionStatus.PENDING)
        .order_by(MemberResultSubmission.reviewed_at.desc(), MemberResultSubmission.id.desc())
        .limit(50)
    ).all()
    return templates.TemplateResponse(
        request,
        "admin/submissions.html",
        {
            "pending_submissions": pending_submissions,
            "reviewed_submissions": reviewed_submissions,
            "summary": summary,
            "errors": errors or [],
        },
        status_code=status_code,
    )


@router.get("/admin/submissions/{submission_id}", response_class=HTMLResponse)
def admin_result_submission_detail(
    submission_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _admin: Member = Depends(require_admin),
) -> HTMLResponse:
    submission = get_submission_or_404(db, submission_id)
    return render_submission_detail(request, submission=submission, admin_view=True)


@router.post("/admin/submissions/{submission_id}/approve")
def approve_result_submission(
    submission_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> Response:
    submission = get_submission_or_404(db, submission_id, for_update=True)
    if (
        submission.status == MemberResultSubmissionStatus.APPROVED
        and submission.result_id is not None
    ):
        return RedirectResponse(f"/results/{submission.result_id}", status_code=303)
    if submission.status != MemberResultSubmissionStatus.PENDING:
        return render_submission_detail(
            request,
            submission=submission,
            admin_view=True,
            errors=["Only pending submissions can be approved."],
            status_code=400,
        )

    result, errors = approve_pending_submission(db, submission, admin)
    if errors:
        db.rollback()
        submission = get_submission_or_404(db, submission_id)
        return render_submission_detail(
            request,
            submission=submission,
            admin_view=True,
            errors=errors,
            status_code=400,
        )
    assert result is not None
    record_submission_approval_audit(db, submission=submission, result=result, admin=admin)
    db.commit()
    return RedirectResponse(f"/results/{result.id}", status_code=303)


@router.post("/admin/submissions/{submission_id}/reject")
def reject_result_submission(
    submission_id: int,
    request: Request,
    rejection_reason: str | None = Form(None),
    db: Session = Depends(get_db),
    admin: Member = Depends(require_admin),
) -> Response:
    submission = get_submission_or_404(db, submission_id, for_update=True)
    if submission.status != MemberResultSubmissionStatus.PENDING:
        return render_submission_detail(
            request,
            submission=submission,
            admin_view=True,
            errors=["Only pending submissions can be rejected."],
            status_code=400,
        )

    cleaned_reason = blank_to_none(rejection_reason)
    submission.status = MemberResultSubmissionStatus.REJECTED
    submission.reviewed_by_member_id = admin.id
    submission.reviewed_at = datetime.now(UTC)
    submission.rejection_reason = cleaned_reason[:500] if cleaned_reason else None
    record_audit(
        db,
        actor=admin,
        action="reject",
        entity_type="member_result_submission",
        entity_id=submission.id,
        summary="Rejected member-submitted result.",
        metadata=submission_audit_metadata(submission),
    )
    db.commit()
    return RedirectResponse("/admin/submissions", status_code=303)


def ensure_member_can_submit(member: Member) -> None:
    if member.deactivated_at is not None or not member.good_standing:
        raise HTTPException(
            status_code=403,
            detail="Only active members in good standing can submit results.",
        )


def submission_select(*, for_update: bool = False):
    statement = select(MemberResultSubmission).options(
        selectinload(MemberResultSubmission.member),
        selectinload(MemberResultSubmission.competition),
        selectinload(MemberResultSubmission.style_subcategory).selectinload(
            StyleSubcategory.category
        ),
        selectinload(MemberResultSubmission.reviewed_by),
        selectinload(MemberResultSubmission.result),
    )
    if for_update:
        statement = statement.with_for_update(of=MemberResultSubmission)
    return statement


def get_submission_or_404(
    db: Session,
    submission_id: int,
    *,
    for_update: bool = False,
) -> MemberResultSubmission:
    submission = db.scalar(
        submission_select(for_update=for_update)
        .where(MemberResultSubmission.id == submission_id)
        .limit(1)
    )
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    return submission


def render_submission_detail(
    request: Request,
    *,
    submission: MemberResultSubmission,
    admin_view: bool = False,
    errors: list[str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "submissions/show.html",
        {
            "submission": submission,
            "admin_view": admin_view,
            "errors": errors or [],
        },
        status_code=status_code,
    )


def save_submission_attachments(
    submission: MemberResultSubmission,
    *,
    photo: UploadFile | None,
    recipe_file: UploadFile | None,
) -> list[str]:
    saved_urls = []
    try:
        if upload_has_file(photo):
            submission.photo_url = save_submission_upload(
                submission_id=submission.id,
                upload=photo,
                kind="photos",
            )
            saved_urls.append(submission.photo_url)
        if upload_has_file(recipe_file):
            submission.recipe_file_url = save_submission_upload(
                submission_id=submission.id,
                upload=recipe_file,
                kind="recipes",
            )
            saved_urls.append(submission.recipe_file_url)
    except ValueError as error:
        for url in saved_urls:
            delete_upload_url(url)
        return [str(error)]
    return []


def approve_pending_submission(
    db: Session,
    submission: MemberResultSubmission,
    admin: Member,
) -> tuple[Result | None, list[str]]:
    errors = validate_result(
        db,
        member_id=submission.member_id,
        competition_id=submission.competition_id,
        style_subcategory_id=submission.style_subcategory_id,
        bjcp_score=submission.bjcp_score,
        place=submission.place,
        placement_scope=submission.placement_scope,
        recipe_url=submission.recipe_url,
    )
    if errors:
        return None, errors
    return approve_submission_with_result(db, submission, reviewer=admin)


def approve_submission_with_result(
    db: Session,
    submission: MemberResultSubmission,
    *,
    reviewer: Member | None,
) -> tuple[Result | None, list[str]]:
    result = Result(
        member_id=submission.member_id,
        competition_id=submission.competition_id,
        style_subcategory_id=submission.style_subcategory_id,
        bjcp_score=submission.bjcp_score,
        place=submission.place,
        placement_scope=submission.placement_scope,
        recipe_url=submission.recipe_url,
        notes=submission.notes,
    )
    db.add(result)
    db.flush()
    attachment_errors = promote_submission_attachments(submission, result)
    if attachment_errors:
        return None, attachment_errors

    submission.status = MemberResultSubmissionStatus.APPROVED
    submission.reviewed_by_member_id = reviewer.id if reviewer is not None else None
    submission.reviewed_at = datetime.now(UTC)
    submission.result_id = result.id
    return result, []


def record_submission_approval_audit(
    db: Session,
    *,
    submission: MemberResultSubmission,
    result: Result,
    admin: Member,
) -> None:
    record_audit(
        db,
        actor=admin,
        action="approve",
        entity_type="member_result_submission",
        entity_id=submission.id,
        summary="Approved member-submitted result.",
        metadata=submission_audit_metadata(submission),
    )
    record_audit(
        db,
        actor=admin,
        action="create",
        entity_type="result",
        entity_id=result.id,
        summary="Created result from member submission.",
        metadata=result_audit_metadata(result),
    )


def promote_submission_attachments(
    submission: MemberResultSubmission,
    result: Result,
) -> list[str]:
    copied_urls = []
    try:
        result.photo_url = copy_upload_url_to_result(
            result_id=result.id,
            url=submission.photo_url,
            kind="photos",
        )
        if result.photo_url and result.photo_url != submission.photo_url:
            copied_urls.append(result.photo_url)
        result.recipe_file_url = copy_upload_url_to_result(
            result_id=result.id,
            url=submission.recipe_file_url,
            kind="recipes",
        )
        if result.recipe_file_url and result.recipe_file_url != submission.recipe_file_url:
            copied_urls.append(result.recipe_file_url)
    except ValueError as error:
        for url in copied_urls:
            delete_upload_url(url)
        return [str(error)]
    return []


def submission_audit_metadata(submission: MemberResultSubmission) -> dict[str, object]:
    return {
        "member_id": submission.member_id,
        "competition_id": submission.competition_id,
        "style_subcategory_id": submission.style_subcategory_id,
        "bjcp_score": (
            str(submission.bjcp_score) if submission.bjcp_score is not None else None
        ),
        "place": submission.place,
        "placement_scope": (
            submission.placement_scope.value if submission.placement_scope else None
        ),
        "status": submission.status.value,
        "result_id": submission.result_id,
    }
