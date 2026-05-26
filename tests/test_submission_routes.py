from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import delete, or_, select

from app.auth import SESSION_COOKIE_NAME, session_token_for_member
from app.db.models import (
    AuditLog,
    Competition,
    CompetitionType,
    Member,
    MemberResultSubmission,
    MemberResultSubmissionStatus,
    PlacementScope,
    Result,
    StyleCategory,
    StyleSubcategory,
)
from app.db.session import SessionLocal
from app.main import app
from app.services.csrf import CSRF_COOKIE_NAME, csrf_token_from_signed_cookie
from app.services.uploads import delete_upload_url


TEST_COMPETITION_NAME = "__Submission Competition__"
TEST_MEMBER_EMAIL = "submission-member@example.test"
TEST_MEMBER_EMAIL_2 = "submission-member-2@example.test"
TEST_GUIDE_YEAR = 2098
TEST_CATEGORY_CODE = "S"
TEST_SUBCATEGORY_CODE = "S1"


def cleanup_submission_data() -> None:
    with SessionLocal() as db:
        competition_ids = list(
            db.scalars(select(Competition.id).where(Competition.name == TEST_COMPETITION_NAME))
        )
        member_ids = list(
            db.scalars(
                select(Member.id).where(
                    Member.email.in_([TEST_MEMBER_EMAIL, TEST_MEMBER_EMAIL_2])
                )
            )
        )
        category = db.scalar(
            select(StyleCategory).where(
                StyleCategory.guide_year == TEST_GUIDE_YEAR,
                StyleCategory.code == TEST_CATEGORY_CODE,
            )
        )
        subcategory_ids = []
        if category is not None:
            subcategory_ids = list(
                db.scalars(
                    select(StyleSubcategory.id).where(
                        StyleSubcategory.category_id == category.id,
                    )
                )
            )

        result_urls = []
        if competition_ids:
            results = db.scalars(
                select(Result).where(Result.competition_id.in_(competition_ids))
            ).all()
            result_urls.extend((result.photo_url, result.recipe_file_url) for result in results)
        if member_ids:
            results = db.scalars(select(Result).where(Result.member_id.in_(member_ids))).all()
            result_urls.extend((result.photo_url, result.recipe_file_url) for result in results)
        if subcategory_ids:
            results = db.scalars(
                select(Result).where(Result.style_subcategory_id.in_(subcategory_ids))
            ).all()
            result_urls.extend((result.photo_url, result.recipe_file_url) for result in results)

        if member_ids:
            db.execute(delete(AuditLog).where(AuditLog.actor_member_id.in_(member_ids)))

        submission_query = select(MemberResultSubmission)
        filters = []
        if member_ids:
            filters.append(MemberResultSubmission.member_id.in_(member_ids))
        if competition_ids:
            filters.append(MemberResultSubmission.competition_id.in_(competition_ids))
        if subcategory_ids:
            filters.append(MemberResultSubmission.style_subcategory_id.in_(subcategory_ids))
        if filters:
            submissions = db.scalars(submission_query.where(or_(*filters))).all()
            for submission in submissions:
                delete_upload_url(submission.photo_url)
                delete_upload_url(submission.recipe_file_url)
            db.execute(
                delete(MemberResultSubmission).where(
                    MemberResultSubmission.id.in_([submission.id for submission in submissions])
                )
            )

        for photo_url, recipe_file_url in result_urls:
            delete_upload_url(photo_url)
            delete_upload_url(recipe_file_url)

        if competition_ids:
            db.execute(delete(Result).where(Result.competition_id.in_(competition_ids)))
        if member_ids:
            db.execute(delete(Result).where(Result.member_id.in_(member_ids)))
        if subcategory_ids:
            db.execute(delete(Result).where(Result.style_subcategory_id.in_(subcategory_ids)))
            db.execute(delete(StyleSubcategory).where(StyleSubcategory.id.in_(subcategory_ids)))
        if category is not None:
            db.delete(category)
        if competition_ids:
            db.execute(delete(Competition).where(Competition.id.in_(competition_ids)))
        if member_ids:
            db.execute(delete(Member).where(Member.id.in_(member_ids)))
        db.commit()


def create_submission_records(
    *,
    good_standing: bool = True,
    submission_review_required: bool = True,
) -> tuple[int, int, int]:
    cleanup_submission_data()
    with SessionLocal() as db:
        member = Member(
            email=TEST_MEMBER_EMAIL,
            display_name="Submission Member",
            good_standing=good_standing,
            submission_review_required=submission_review_required,
        )
        competition = Competition(
            name=TEST_COMPETITION_NAME,
            date=date(2026, 5, 18),
            competition_type=CompetitionType.BJCP_SANCTIONED,
        )
        category = StyleCategory(
            guide_year=TEST_GUIDE_YEAR,
            code=TEST_CATEGORY_CODE,
            name="Submission Styles",
        )
        subcategory = StyleSubcategory(
            category=category,
            code=TEST_SUBCATEGORY_CODE,
            name="Submission Style",
        )
        db.add_all([member, competition, subcategory])
        db.commit()
        return member.id, competition.id, subcategory.id


def member_client(member_id: int) -> TestClient:
    with SessionLocal() as db:
        member = db.get(Member, member_id)
        assert member is not None
        token = session_token_for_member(member)
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    client.get("/results")
    return client


def csrf_token(client: TestClient) -> str:
    token = csrf_token_from_signed_cookie(client.cookies.get(CSRF_COOKIE_NAME))
    assert token is not None
    return token


def submit_result(
    client: TestClient,
    competition_id: int,
    subcategory_id: int,
    *,
    files: dict[str, tuple[str, bytes, str]] | None = None,
) -> int:
    response = client.post(
        "/me/results",
        data={
            "competition_id": str(competition_id),
            "style_subcategory_id": str(subcategory_id),
            "bjcp_score": "41.0",
            "place": "4",
            "placement_scope": PlacementScope.CATEGORY.value,
            "recipe_url": "",
            "notes": "Member submitted this.",
            "csrf_token": csrf_token(client),
        },
        files=files,
        follow_redirects=False,
    )
    assert response.status_code == 303
    with SessionLocal() as db:
        submission = db.scalar(
            select(MemberResultSubmission).where(
                MemberResultSubmission.competition_id == competition_id
            )
        )
        assert submission is not None
        return submission.id


def test_member_can_submit_result_and_admin_can_approve(admin_client) -> None:
    member_id, competition_id, subcategory_id = create_submission_records()
    try:
        client = member_client(member_id)

        form_response = client.get("/me/results/new")
        assert form_response.status_code == 200
        assert "Submit result" in form_response.text
        assert "Submission Member" in form_response.text
        assert "HM" in form_response.text

        submission_id = submit_result(client, competition_id, subcategory_id)
        with SessionLocal() as db:
            submission = db.get(MemberResultSubmission, submission_id)
            assert submission is not None
            assert submission.status == MemberResultSubmissionStatus.PENDING
            assert submission.place == 4
            assert db.scalar(select(Result).where(Result.member_id == member_id)) is None

        review_response = admin_client.get("/admin/submissions")
        assert review_response.status_code == 200
        assert "Submission Member" in review_response.text
        assert "HM" in review_response.text

        approve_response = admin_client.post(
            f"/admin/submissions/{submission_id}/approve",
            follow_redirects=False,
        )
        assert approve_response.status_code == 303
        assert approve_response.headers["location"].startswith("/results/")

        with SessionLocal() as db:
            submission = db.get(MemberResultSubmission, submission_id)
            result = db.scalar(select(Result).where(Result.member_id == member_id))
            assert submission is not None
            assert result is not None
            result_id = result.id
            assert submission.status == MemberResultSubmissionStatus.APPROVED
            assert submission.result_id == result.id
            assert result.bjcp_score == Decimal("41.0")
            assert result.place == 4
            assert result.notes == "Member submitted this."

        second_approve_response = admin_client.post(
            f"/admin/submissions/{submission_id}/approve",
            follow_redirects=False,
        )
        assert second_approve_response.status_code == 303
        assert second_approve_response.headers["location"] == f"/results/{result_id}"
        with SessionLocal() as db:
            result_ids = list(
                db.scalars(select(Result.id).where(Result.member_id == member_id))
            )
            assert result_ids == [result_id]

        result_response = admin_client.get(approve_response.headers["location"])
        assert result_response.status_code == 200
        assert "HM in category" in result_response.text
    finally:
        cleanup_submission_data()


def test_admin_approval_copies_submission_uploads_to_result(admin_client) -> None:
    member_id, competition_id, subcategory_id = create_submission_records()
    try:
        client = member_client(member_id)
        submission_id = submit_result(
            client,
            competition_id,
            subcategory_id,
            files={
                "photo": ("entry.png", b"fake image bytes", "image/png"),
                "recipe_file": ("recipe.pdf", b"%PDF-1.4 fake pdf", "application/pdf"),
            },
        )
        with SessionLocal() as db:
            submission = db.get(MemberResultSubmission, submission_id)
            assert submission is not None
            submission_photo_url = submission.photo_url
            submission_recipe_file_url = submission.recipe_file_url
            assert submission_photo_url is not None
            assert submission_recipe_file_url is not None
            assert submission_photo_url.startswith(
                f"/uploads/submissions/{submission.id}/photos/"
            )
            assert submission_recipe_file_url.startswith(
                f"/uploads/submissions/{submission.id}/recipes/"
            )

        assert admin_client.get(submission_photo_url).status_code == 200
        assert admin_client.get(submission_recipe_file_url).status_code == 200

        approve_response = admin_client.post(
            f"/admin/submissions/{submission_id}/approve",
            follow_redirects=False,
        )
        assert approve_response.status_code == 303

        with SessionLocal() as db:
            result = db.scalar(select(Result).where(Result.member_id == member_id))
            assert result is not None
            result_photo_url = result.photo_url
            result_recipe_file_url = result.recipe_file_url
            assert result_photo_url is not None
            assert result_recipe_file_url is not None
            assert result_photo_url.startswith(f"/uploads/results/{result.id}/photos/")
            assert result_recipe_file_url.startswith(f"/uploads/results/{result.id}/recipes/")
            assert result_photo_url != submission_photo_url
            assert result_recipe_file_url != submission_recipe_file_url

        assert admin_client.get(result_photo_url).status_code == 200
        assert admin_client.get(result_recipe_file_url).status_code == 200
        assert admin_client.get(submission_photo_url).status_code == 200
        assert admin_client.get(submission_recipe_file_url).status_code == 200
    finally:
        cleanup_submission_data()


def test_admin_can_bulk_approve_pending_submissions(admin_client) -> None:
    member_id, competition_id, subcategory_id = create_submission_records()
    try:
        client = member_client(member_id)
        first_submission_id = submit_result(client, competition_id, subcategory_id)
        with SessionLocal() as db:
            second_member = Member(
                email=TEST_MEMBER_EMAIL_2,
                display_name="Second Submission Member",
                good_standing=True,
            )
            db.add(second_member)
            db.flush()
            second_submission = MemberResultSubmission(
                member_id=second_member.id,
                competition_id=competition_id,
                style_subcategory_id=subcategory_id,
                bjcp_score=Decimal("39.0"),
                place=3,
                placement_scope=PlacementScope.CATEGORY,
                notes="Second pending submission.",
            )
            db.add(second_submission)
            db.commit()
            second_submission_id = second_submission.id

        response = admin_client.post("/admin/submissions/approve-all")

        assert response.status_code == 200
        assert "Approved 2 pending submissions." in response.text
        with SessionLocal() as db:
            submissions = db.scalars(
                select(MemberResultSubmission).where(
                    MemberResultSubmission.id.in_(
                        [first_submission_id, second_submission_id]
                    )
                )
            ).all()
            result_count = len(
                db.scalars(
                    select(Result).where(Result.competition_id == competition_id)
                ).all()
            )
            assert {submission.status for submission in submissions} == {
                MemberResultSubmissionStatus.APPROVED
            }
            assert result_count == 2
    finally:
        cleanup_submission_data()


def test_trusted_member_submission_publishes_without_admin_review(admin_client) -> None:
    member_id, competition_id, subcategory_id = create_submission_records(
        submission_review_required=False,
    )
    try:
        client = member_client(member_id)
        form_response = client.get("/me/results/new")
        assert form_response.status_code == 200
        assert "Submit Result" in form_response.text
        assert "Submit for Review" not in form_response.text

        submission_id = submit_result(
            client,
            competition_id,
            subcategory_id,
            files={
                "photo": ("trusted-entry.png", b"fake image bytes", "image/png"),
                "recipe_file": ("trusted-recipe.pdf", b"%PDF-1.4 fake pdf", "application/pdf"),
            },
        )

        with SessionLocal() as db:
            submission = db.get(MemberResultSubmission, submission_id)
            result = db.scalar(select(Result).where(Result.member_id == member_id))
            pending_submission_id = db.scalar(
                select(MemberResultSubmission.id)
                .where(
                    MemberResultSubmission.member_id == member_id,
                    MemberResultSubmission.status == MemberResultSubmissionStatus.PENDING,
                )
                .limit(1)
            )
            assert submission is not None
            assert result is not None
            assert pending_submission_id is None
            assert submission.status == MemberResultSubmissionStatus.APPROVED
            assert submission.result_id == result.id
            assert submission.reviewed_by_member_id is None
            assert result.photo_url is not None
            assert result.recipe_file_url is not None
            assert result.photo_url.startswith(f"/uploads/results/{result.id}/photos/")
            assert result.recipe_file_url.startswith(f"/uploads/results/{result.id}/recipes/")
            result_photo_url = result.photo_url
            result_recipe_file_url = result.recipe_file_url

        assert client.get(result_photo_url).status_code == 200
        assert client.get(result_recipe_file_url).status_code == 200
    finally:
        cleanup_submission_data()


def test_admin_can_reject_member_submission(admin_client) -> None:
    member_id, competition_id, subcategory_id = create_submission_records()
    try:
        client = member_client(member_id)
        submission_id = submit_result(client, competition_id, subcategory_id)

        reject_response = admin_client.post(
            f"/admin/submissions/{submission_id}/reject",
            data={"rejection_reason": "Please include the score sheet."},
            follow_redirects=False,
        )
        assert reject_response.status_code == 303
        assert reject_response.headers["location"] == "/admin/submissions"

        with SessionLocal() as db:
            submission = db.get(MemberResultSubmission, submission_id)
            assert submission is not None
            assert submission.status == MemberResultSubmissionStatus.REJECTED
            assert submission.rejection_reason == "Please include the score sheet."
            assert db.scalar(select(Result).where(Result.member_id == member_id)) is None

        member_response = client.get(f"/me/submissions/{submission_id}")
        assert member_response.status_code == 200
        assert "Rejected" in member_response.text
        assert "Please include the score sheet." in member_response.text
    finally:
        cleanup_submission_data()


def test_member_submission_requires_login() -> None:
    response = TestClient(app).get("/me/results/new", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/member-login?next=%2Fme%2Fresults%2Fnew"


def test_member_not_in_good_standing_cannot_submit() -> None:
    member_id, _, _ = create_submission_records(good_standing=False)
    try:
        response = member_client(member_id).get("/me/results/new")

        assert response.status_code == 403
        assert response.json()["detail"] == "Only active members in good standing can submit results."
    finally:
        cleanup_submission_data()
