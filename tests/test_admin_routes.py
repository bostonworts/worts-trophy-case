from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import delete, or_, select

from app.db.models import (
    AuditLog,
    Competition,
    CompetitionType,
    Member,
    MemberEmail,
    MemberEmailKind,
    MemberResultSubmission,
    MemberResultSubmissionStatus,
    PlacementScope,
    Result,
    StyleCategory,
    StyleSubcategory,
)
from app.db.session import SessionLocal
from app.main import app
from app.services.uploads import delete_upload_url, path_to_url, upload_root


ADMIN_MEMBER_EMAIL = "admin-tools-member@example.test"
ADMIN_MEMBER_PAYPAL_EMAIL = "admin-tools-paypal@example.test"
ADMIN_MEMBER_LIST_EMAIL = "admin-tools-list@example.test"
ADMIN_COMPETITION_NAME = "__Admin Tools Competition__"
ADMIN_GUIDE_YEAR = 2093
ADMIN_CATEGORY_CODE = "88"
ADMIN_SUBCATEGORY_CODE = "88A"


def cleanup_admin_tools_data() -> None:
    with SessionLocal() as db:
        member_emails = [
            ADMIN_MEMBER_EMAIL,
            ADMIN_MEMBER_PAYPAL_EMAIL,
            ADMIN_MEMBER_LIST_EMAIL,
        ]
        member = db.scalar(select(Member).where(Member.email.in_(member_emails)))
        alias_member_id = db.scalar(
            select(MemberEmail.member_id).where(MemberEmail.email.in_(member_emails))
        )
        if member is None and alias_member_id is not None:
            member = db.get(Member, alias_member_id)
        competitions = list(
            db.scalars(select(Competition).where(Competition.name == ADMIN_COMPETITION_NAME))
        )
        category = db.scalar(
            select(StyleCategory).where(
                StyleCategory.guide_year == ADMIN_GUIDE_YEAR,
                StyleCategory.code == ADMIN_CATEGORY_CODE,
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
        competition_ids = [competition.id for competition in competitions]
        result_urls = []
        if competition_ids:
            results = db.scalars(
                select(Result).where(Result.competition_id.in_(competition_ids))
            ).all()
            result_urls.extend((result.photo_url, result.recipe_file_url) for result in results)
        if member is not None:
            results = db.scalars(select(Result).where(Result.member_id == member.id)).all()
            result_urls.extend((result.photo_url, result.recipe_file_url) for result in results)
        if subcategory_ids:
            results = db.scalars(
                select(Result).where(Result.style_subcategory_id.in_(subcategory_ids))
            ).all()
            result_urls.extend((result.photo_url, result.recipe_file_url) for result in results)

        submission_filters = []
        if member is not None:
            submission_filters.append(MemberResultSubmission.member_id == member.id)
        if competition_ids:
            submission_filters.append(MemberResultSubmission.competition_id.in_(competition_ids))
        if subcategory_ids:
            submission_filters.append(
                MemberResultSubmission.style_subcategory_id.in_(subcategory_ids)
            )
        if submission_filters:
            submissions = db.scalars(
                select(MemberResultSubmission).where(or_(*submission_filters))
            ).all()
            result_urls.extend(
                (submission.photo_url, submission.recipe_file_url)
                for submission in submissions
            )
            db.execute(
                delete(MemberResultSubmission).where(
                    MemberResultSubmission.id.in_(
                        [submission.id for submission in submissions]
                    )
                )
            )

        for photo_url, recipe_file_url in result_urls:
            delete_upload_url(photo_url)
            delete_upload_url(recipe_file_url)

        if competition_ids:
            db.execute(delete(Result).where(Result.competition_id.in_(competition_ids)))
        if member is not None:
            db.execute(delete(Result).where(Result.member_id == member.id))
        if subcategory_ids:
            db.execute(delete(Result).where(Result.style_subcategory_id.in_(subcategory_ids)))
            db.execute(delete(StyleSubcategory).where(StyleSubcategory.id.in_(subcategory_ids)))
        if category is not None:
            db.delete(category)
        if competitions:
            db.execute(delete(Competition).where(Competition.id.in_(competition_ids)))
        if member is not None:
            db.delete(member)
        db.commit()


def create_admin_tools_result() -> int:
    cleanup_admin_tools_data()
    with SessionLocal() as db:
        member = Member(
            email=ADMIN_MEMBER_EMAIL,
            display_name="Admin Tools Member",
            good_standing=False,
        )
        db.add(member)
        db.flush()
        db.add_all(
            [
                MemberEmail(
                    member=member,
                    email=ADMIN_MEMBER_PAYPAL_EMAIL,
                    kind=MemberEmailKind.PAYPAL,
                ),
                MemberEmail(
                    member=member,
                    email=ADMIN_MEMBER_LIST_EMAIL,
                    kind=MemberEmailKind.MAILING_LIST,
                ),
            ]
        )
        competition = Competition(
            name=ADMIN_COMPETITION_NAME,
            date=date(2026, 5, 18),
            competition_type=CompetitionType.BJCP_SANCTIONED,
        )
        category = StyleCategory(
            guide_year=ADMIN_GUIDE_YEAR,
            code=ADMIN_CATEGORY_CODE,
            name="Admin Tools Category",
        )
        subcategory = StyleSubcategory(
            category=category,
            code=ADMIN_SUBCATEGORY_CODE,
            name="Admin Tools Style",
        )
        result = Result(
            member=member,
            competition=competition,
            style_subcategory=subcategory,
            bjcp_score=Decimal("41.0"),
            place=1,
            placement_scope=PlacementScope.CATEGORY,
        )
        db.add(result)
        db.commit()
        return result.id


def create_admin_tools_submission(result_id: int) -> int:
    with SessionLocal() as db:
        result = db.get(Result, result_id)
        assert result is not None
        submission = MemberResultSubmission(
            member_id=result.member_id,
            competition_id=result.competition_id,
            style_subcategory_id=result.style_subcategory_id,
            bjcp_score=result.bjcp_score,
            place=result.place,
            placement_scope=result.placement_scope,
            recipe_url="https://example.test/admin-tools-recipe",
            notes="Admin backup submission.",
            status=MemberResultSubmissionStatus.APPROVED,
            reviewed_at=datetime.now(UTC),
            result_id=result.id,
        )
        db.add(submission)
        db.commit()
        return submission.id


def create_admin_tools_archived_submission() -> tuple[int, int, int]:
    cleanup_admin_tools_data()
    with SessionLocal() as db:
        member = Member(
            email=ADMIN_MEMBER_EMAIL,
            display_name="Admin Tools Member",
            deactivated_at=datetime.now(UTC),
        )
        competition = Competition(
            name=ADMIN_COMPETITION_NAME,
            date=date(2026, 5, 18),
            competition_type=CompetitionType.BJCP_SANCTIONED,
            archived_at=datetime.now(UTC),
        )
        category = StyleCategory(
            guide_year=ADMIN_GUIDE_YEAR,
            code=ADMIN_CATEGORY_CODE,
            name="Admin Tools Category",
        )
        subcategory = StyleSubcategory(
            category=category,
            code=ADMIN_SUBCATEGORY_CODE,
            name="Admin Tools Style",
        )
        submission = MemberResultSubmission(
            member=member,
            competition=competition,
            style_subcategory=subcategory,
            bjcp_score=Decimal("38.0"),
            notes="Pending archived submission.",
        )
        db.add(submission)
        db.commit()
        return competition.id, member.id, submission.id


def attach_recipe_file(result_id: int) -> str:
    target = upload_root() / "results" / str(result_id) / "recipes" / "clear-test.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("recipe", encoding="utf-8")
    url = path_to_url(target)
    with SessionLocal() as db:
        result = db.get(Result, result_id)
        assert result is not None
        result.recipe_file_url = url
        db.commit()
    return url


def test_admin_dashboard_requires_admin(admin_client) -> None:
    public_response = TestClient(app).get("/admin", follow_redirects=False)
    admin_response = admin_client.get("/admin")

    assert public_response.status_code == 303
    assert public_response.headers["location"].startswith("/login")
    assert admin_response.status_code == 200
    assert "Dashboard" in admin_response.text
    assert "Data Tools" in admin_response.text


def test_admin_backup_and_restore_round_trip(admin_client) -> None:
    result_id = create_admin_tools_result()
    create_admin_tools_submission(result_id)
    try:
        backup_response = admin_client.get("/admin/data/backup.json")
        assert backup_response.status_code == 200
        backup = json.loads(backup_response.text)
        assert backup["format"] == "trophy-case.backup.v1"
        assert ADMIN_MEMBER_EMAIL in backup_response.text
        assert ADMIN_MEMBER_PAYPAL_EMAIL in backup_response.text
        assert ADMIN_MEMBER_LIST_EMAIL in backup_response.text
        assert "member_result_submissions" in backup
        assert "Admin backup submission." in backup_response.text

        cleanup_admin_tools_data()
        restore_response = admin_client.post(
            "/admin/data/restore",
            files={
                "backup_file": (
                    "backup.json",
                    json.dumps(backup).encode(),
                    "application/json",
                )
            },
        )

        assert restore_response.status_code == 200
        assert "Restored" in restore_response.text
        with SessionLocal() as db:
            restored_member = db.scalar(select(Member).where(Member.email == ADMIN_MEMBER_EMAIL))
            restored_competition = db.scalar(
                select(Competition).where(Competition.name == ADMIN_COMPETITION_NAME)
            )
            restored_result = db.scalar(
                select(Result)
                .join(Result.member)
                .where(Member.email == ADMIN_MEMBER_EMAIL)
            )
            assert restored_member is not None
            assert restored_member.good_standing is False
            assert restored_competition is not None
            assert restored_result is not None
            assert restored_result.bjcp_score == Decimal("41.0")
            restored_submission = db.scalar(
                select(MemberResultSubmission)
                .join(MemberResultSubmission.member)
                .where(Member.email == ADMIN_MEMBER_EMAIL)
            )
            assert restored_submission is not None
            assert restored_submission.status == MemberResultSubmissionStatus.APPROVED
            assert restored_submission.result_id == restored_result.id
            assert restored_submission.notes == "Admin backup submission."
            aliases = {
                alias.kind: alias.email
                for alias in db.scalars(
                    select(MemberEmail).where(MemberEmail.member_id == restored_member.id)
                )
            }
            assert aliases[MemberEmailKind.PAYPAL] == ADMIN_MEMBER_PAYPAL_EMAIL
            assert aliases[MemberEmailKind.MAILING_LIST] == ADMIN_MEMBER_LIST_EMAIL
    finally:
        cleanup_admin_tools_data()


def test_admin_clear_results_requires_confirmation(admin_client) -> None:
    result_id = create_admin_tools_result()
    try:
        bad_response = admin_client.post(
            "/admin/data/clear-results",
            data={"confirm_text": "nope"},
        )
        assert bad_response.status_code == 400
        with SessionLocal() as db:
            assert db.get(Result, result_id) is not None

        good_response = admin_client.post(
            "/admin/data/clear-results",
            data={"confirm_text": "CLEAR RESULTS"},
        )

        assert good_response.status_code == 200
        assert "Deleted" in good_response.text
        with SessionLocal() as db:
            assert db.get(Result, result_id) is None
    finally:
        cleanup_admin_tools_data()


def test_admin_clear_results_deletes_uploaded_files(admin_client) -> None:
    result_id = create_admin_tools_result()
    recipe_file_url = attach_recipe_file(result_id)
    try:
        assert admin_client.get(recipe_file_url).status_code == 200

        response = admin_client.post(
            "/admin/data/clear-results",
            data={"confirm_text": "CLEAR RESULTS"},
        )

        assert response.status_code == 200
        assert admin_client.get(recipe_file_url).status_code == 404
    finally:
        cleanup_admin_tools_data()


def test_admin_clear_archive_keeps_records_with_submissions(admin_client) -> None:
    competition_id, member_id, submission_id = create_admin_tools_archived_submission()
    try:
        response = admin_client.post(
            "/admin/data/clear-archive",
            data={"confirm_text": "CLEAR ARCHIVE"},
        )

        assert response.status_code == 200
        with SessionLocal() as db:
            assert db.get(Competition, competition_id) is not None
            assert db.get(Member, member_id) is not None
            assert db.get(MemberResultSubmission, submission_id) is not None
    finally:
        cleanup_admin_tools_data()


def test_admin_leaderboard_settings_change_scores(admin_client) -> None:
    create_admin_tools_result()
    try:
        data = {
            "season_start_month": "7",
            "season_start_day": "1",
            "place_1_points": "10",
            "place_2_points": "5",
            "place_3_points": "2",
            "place_4_points": "1",
            "best_of_show_multiplier": "2",
            "high_profile_bonus": "0",
            "minimum_bjcp_score": "40",
        }
        for competition_type in CompetitionType:
            data[f"weight_{competition_type.value}"] = (
                "0" if competition_type == CompetitionType.CLUB_ONLY else "1"
            )

        settings_response = admin_client.post("/admin/leaderboard", data=data)
        leaderboard_response = admin_client.get("/leaderboard?season=2025-2026")

        assert settings_response.status_code == 200
        assert "Leaderboard settings saved." in settings_response.text
        assert leaderboard_response.status_code == 200
        assert "Admin Tools Member" in leaderboard_response.text
        assert "10" in leaderboard_response.text
    finally:
        cleanup_admin_tools_data()


def test_admin_leaderboard_settings_validate_dates(admin_client) -> None:
    data = {
        "season_start_month": "2",
        "season_start_day": "31",
        "place_1_points": "3",
        "place_2_points": "2",
        "place_3_points": "1",
        "place_4_points": "0.5",
        "best_of_show_multiplier": "2",
        "high_profile_bonus": "0.5",
        "minimum_bjcp_score": "",
    }
    for competition_type in CompetitionType:
        data[f"weight_{competition_type.value}"] = "1"

    response = admin_client.post("/admin/leaderboard", data=data)

    assert response.status_code == 400
    assert "Season start month and day must make a valid date." in response.text


def test_admin_audit_log_records_cleanup(admin_client) -> None:
    create_admin_tools_result()
    try:
        clear_response = admin_client.post(
            "/admin/data/clear-results",
            data={"confirm_text": "CLEAR RESULTS"},
        )
        audit_response = admin_client.get("/admin/audit")

        assert clear_response.status_code == 200
        assert audit_response.status_code == 200
        assert "Deleted" in audit_response.text
        with SessionLocal() as db:
            audit_entry = db.scalar(
                select(AuditLog).where(
                    AuditLog.action == "clear",
                    AuditLog.entity_type == "results",
                )
            )
            assert audit_entry is not None
    finally:
        cleanup_admin_tools_data()
