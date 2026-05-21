from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
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
from app.main import app


TEST_COMPETITION_NAME = "__Profile Competition__"
TEST_MEMBER_EMAIL = "profile-member@example.test"
TEST_GUIDE_YEAR = 2094
TEST_CATEGORY_CODE = "P"
TEST_SUBCATEGORY_CODE = "P1"


def cleanup_profile_data() -> None:
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


def create_profile_result(
    *,
    archived_competition: bool = False,
    archived_result: bool = False,
) -> tuple[int, int, int]:
    cleanup_profile_data()
    archived_at = datetime.now(UTC)
    with SessionLocal() as db:
        member = Member(email=TEST_MEMBER_EMAIL, display_name="Profile Member")
        competition = Competition(
            name=TEST_COMPETITION_NAME,
            date=date(2026, 5, 18),
            competition_type=CompetitionType.BJCP_SANCTIONED,
            url="https://example.test/profile-competition",
            archived_at=archived_at if archived_competition else None,
        )
        category = StyleCategory(
            guide_year=TEST_GUIDE_YEAR,
            code=TEST_CATEGORY_CODE,
            name="Profile Styles",
        )
        subcategory = StyleSubcategory(
            category=category,
            code=TEST_SUBCATEGORY_CODE,
            name="Profile Style",
        )
        result = Result(
            member=member,
            competition=competition,
            style_subcategory=subcategory,
            bjcp_score=Decimal("42.0"),
            place=1,
            placement_scope=PlacementScope.CATEGORY,
            archived_at=archived_at if archived_result else None,
        )
        db.add(result)
        db.commit()
        return member.id, competition.id, result.id


def test_public_member_profile_shows_visible_results() -> None:
    member_id, competition_id, result_id = create_profile_result()
    try:
        response = TestClient(app).get(f"/members/{member_id}")

        assert response.status_code == 200
        assert "Profile Member" in response.text
        assert TEST_MEMBER_EMAIL not in response.text
        assert TEST_COMPETITION_NAME in response.text
        assert "P1 Profile Style" in response.text
        assert "3 leaderboard points" in response.text
        assert f'href="/results?member_id={member_id}"' in response.text
        assert f'href="/competitions/{competition_id}"' in response.text
        assert f'href="/results/{result_id}"' in response.text
    finally:
        cleanup_profile_data()


def test_public_competition_profile_shows_visible_results_and_filter_link() -> None:
    member_id, competition_id, result_id = create_profile_result()
    try:
        client = TestClient(app)

        profile_response = client.get(f"/competitions/{competition_id}")
        filtered_response = client.get(f"/results?competition_id={competition_id}")

        assert profile_response.status_code == 200
        assert TEST_COMPETITION_NAME in profile_response.text
        assert "Profile Member" in profile_response.text
        assert "P1 Profile Style" in profile_response.text
        assert "3 pts" in profile_response.text
        assert f'href="/results?competition_id={competition_id}"' in profile_response.text
        assert f'href="/members/{member_id}"' in profile_response.text
        assert f'href="/results/{result_id}"' in profile_response.text
        assert filtered_response.status_code == 200
        assert f'href="/results/{result_id}"' in filtered_response.text
    finally:
        cleanup_profile_data()


def test_public_cannot_view_archived_competition_profile_but_admin_can(admin_client) -> None:
    _, competition_id, result_id = create_profile_result(archived_competition=True)
    try:
        public_response = TestClient(app).get(f"/competitions/{competition_id}")
        admin_response = admin_client.get(f"/competitions/{competition_id}")

        assert public_response.status_code == 404
        assert admin_response.status_code == 200
        assert "This competition is archived." in admin_response.text
        assert "Hidden results" in admin_response.text
        assert f'href="/results/{result_id}"' in admin_response.text
    finally:
        cleanup_profile_data()


def test_admin_member_profile_shows_hidden_results(admin_client) -> None:
    member_id, _, result_id = create_profile_result(archived_result=True)
    try:
        public_response = TestClient(app).get(f"/members/{member_id}")
        admin_response = admin_client.get(f"/members/{member_id}")

        assert public_response.status_code == 200
        assert f'href="/results/{result_id}"' not in public_response.text
        assert "No public results for this member." in public_response.text
        assert admin_response.status_code == 200
        assert "Hidden results" in admin_response.text
        assert "Result archived" in admin_response.text
        assert f'href="/results/{result_id}"' in admin_response.text
    finally:
        cleanup_profile_data()
