from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select

from app.db.models import (
    Competition,
    CompetitionType,
    Member,
    PlacementScope,
    Result,
    StyleCategory,
    StyleSubcategory,
)
from app.db.session import SessionLocal


TEST_COMPETITION_NAME = "__Archive Competition__"
TEST_MEMBER_EMAIL = "archive-member@example.test"
TEST_GUIDE_YEAR = 2097
TEST_CATEGORY_CODE = "A"
TEST_SUBCATEGORY_CODE = "A1"


def cleanup_archive_data() -> None:
    with SessionLocal() as db:
        competition_ids = list(
            db.scalars(select(Competition.id).where(Competition.name == TEST_COMPETITION_NAME))
        )
        member_ids = list(db.scalars(select(Member.id).where(Member.email == TEST_MEMBER_EMAIL)))
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


def create_archive_records() -> tuple[int, int, int, int]:
    cleanup_archive_data()
    with SessionLocal() as db:
        member = Member(email=TEST_MEMBER_EMAIL, display_name="Archive Member")
        competition = Competition(
            name=TEST_COMPETITION_NAME,
            date=date(2026, 5, 18),
            competition_type=CompetitionType.BJCP_SANCTIONED,
        )
        category = StyleCategory(
            guide_year=TEST_GUIDE_YEAR,
            code=TEST_CATEGORY_CODE,
            name="Archive Styles",
        )
        subcategory = StyleSubcategory(
            category=category,
            code=TEST_SUBCATEGORY_CODE,
            name="Archive Style",
        )
        result = Result(
            member=member,
            competition=competition,
            style_subcategory=subcategory,
            bjcp_score=Decimal("40.0"),
            place=1,
            placement_scope=PlacementScope.CATEGORY,
        )
        db.add(result)
        db.commit()
        return member.id, competition.id, subcategory.id, result.id


def test_competition_can_be_archived_and_restored(admin_client) -> None:
    _, competition_id, _, _ = create_archive_records()
    try:
        client = admin_client

        archive_response = client.post(
            f"/competitions/{competition_id}/archive",
            follow_redirects=False,
        )

        assert archive_response.status_code == 303
        assert archive_response.headers["location"] == "/competitions"
        with SessionLocal() as db:
            competition = db.get(Competition, competition_id)
            assert competition is not None
            assert competition.archived_at is not None

        result_form = client.get("/results/new")
        assert TEST_COMPETITION_NAME not in result_form.text

        restore_response = client.post(
            f"/competitions/{competition_id}/restore",
            follow_redirects=False,
        )

        assert restore_response.status_code == 303
        with SessionLocal() as db:
            competition = db.get(Competition, competition_id)
            assert competition is not None
            assert competition.archived_at is None
    finally:
        cleanup_archive_data()


def test_result_can_be_archived_and_restored(admin_client) -> None:
    _, _, _, result_id = create_archive_records()
    try:
        client = admin_client

        archive_response = client.post(f"/results/{result_id}/archive", follow_redirects=False)

        assert archive_response.status_code == 303
        with SessionLocal() as db:
            result = db.get(Result, result_id)
            assert result is not None
            assert result.archived_at is not None

        leaderboard = client.get("/leaderboard?season=2025-2026")
        assert "Archive Member" not in leaderboard.text
        results_page = client.get("/results")
        assert "Archived results" in results_page.text
        assert "Archive Member" in results_page.text

        restore_response = client.post(f"/results/{result_id}/restore", follow_redirects=False)

        assert restore_response.status_code == 303
        with SessionLocal() as db:
            result = db.get(Result, result_id)
            assert result is not None
            assert result.archived_at is None
    finally:
        cleanup_archive_data()


def test_member_can_be_reactivated(admin_client) -> None:
    member_id, _, _, _ = create_archive_records()
    try:
        client = admin_client
        deactivate_response = client.post(
            f"/members/{member_id}/deactivate",
            follow_redirects=False,
        )
        assert deactivate_response.status_code == 303

        reactivate_response = client.post(
            f"/members/{member_id}/reactivate",
            follow_redirects=False,
        )

        assert reactivate_response.status_code == 303
        with SessionLocal() as db:
            member = db.get(Member, member_id)
            assert member is not None
            assert member.deactivated_at is None
    finally:
        cleanup_archive_data()
