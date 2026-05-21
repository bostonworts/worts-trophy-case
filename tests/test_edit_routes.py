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


TEST_COMPETITION_NAME = "__Edit Competition__"
TEST_COMPETITION_UPDATED_NAME = "__Edited Competition__"
TEST_MEMBER_EMAIL = "edit-member@example.test"
TEST_MEMBER_UPDATED_EMAIL = "edited-member@example.test"
TEST_GUIDE_YEAR = 2098
TEST_CATEGORY_CODE = "E"
TEST_SUBCATEGORY_CODE = "E1"


def cleanup_edit_data() -> None:
    with SessionLocal() as db:
        competition_ids = list(
            db.scalars(
                select(Competition.id).where(
                    Competition.name.in_(
                        [TEST_COMPETITION_NAME, TEST_COMPETITION_UPDATED_NAME]
                    )
                )
            )
        )
        member_ids = list(
            db.scalars(
                select(Member.id).where(
                    Member.email.in_([TEST_MEMBER_EMAIL, TEST_MEMBER_UPDATED_EMAIL])
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


def create_edit_records() -> tuple[int, int, int, int]:
    cleanup_edit_data()
    with SessionLocal() as db:
        member = Member(email=TEST_MEMBER_EMAIL, display_name="Edit Member")
        competition = Competition(
            name=TEST_COMPETITION_NAME,
            date=date(2026, 5, 18),
            competition_type=CompetitionType.BJCP_SANCTIONED,
        )
        category = StyleCategory(
            guide_year=TEST_GUIDE_YEAR,
            code=TEST_CATEGORY_CODE,
            name="Edit Styles",
        )
        subcategory = StyleSubcategory(
            category=category,
            code=TEST_SUBCATEGORY_CODE,
            name="Edit Style",
        )
        result = Result(
            member=member,
            competition=competition,
            style_subcategory=subcategory,
            bjcp_score=Decimal("38.0"),
            place=3,
            placement_scope=PlacementScope.CATEGORY,
            notes="Original notes",
        )
        db.add(result)
        db.commit()
        return member.id, competition.id, subcategory.id, result.id


def test_competition_can_be_edited(admin_client) -> None:
    _, competition_id, _, _ = create_edit_records()
    try:
        client = admin_client

        edit_page = client.get(f"/competitions/{competition_id}/edit")
        assert edit_page.status_code == 200
        assert TEST_COMPETITION_NAME in edit_page.text

        response = client.post(
            f"/competitions/{competition_id}",
            data={
                "name": TEST_COMPETITION_UPDATED_NAME,
                "date": "2026-06-01",
                "competition_type": CompetitionType.NHC_QUALIFIER.value,
                "url": "https://example.test/edited",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/competitions"
        with SessionLocal() as db:
            competition = db.get(Competition, competition_id)
            assert competition is not None
            assert competition.name == TEST_COMPETITION_UPDATED_NAME
            assert competition.date == date(2026, 6, 1)
            assert competition.competition_type == CompetitionType.NHC_QUALIFIER
            assert competition.url == "https://example.test/edited"
    finally:
        cleanup_edit_data()


def test_member_can_be_edited(admin_client) -> None:
    member_id, _, _, _ = create_edit_records()
    try:
        client = admin_client

        edit_page = client.get(f"/members/{member_id}/edit")
        assert edit_page.status_code == 200
        assert TEST_MEMBER_EMAIL in edit_page.text

        response = client.post(
            f"/members/{member_id}",
            data={
                "display_name": "Edited Member",
                "email": TEST_MEMBER_UPDATED_EMAIL,
                "is_admin": "true",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/members"
        with SessionLocal() as db:
            member = db.get(Member, member_id)
            assert member is not None
            assert member.display_name == "Edited Member"
            assert member.email == TEST_MEMBER_UPDATED_EMAIL
            assert member.is_admin
    finally:
        cleanup_edit_data()


def test_result_can_be_edited(admin_client) -> None:
    member_id, competition_id, subcategory_id, result_id = create_edit_records()
    try:
        client = admin_client

        edit_page = client.get(f"/results/{result_id}/edit")
        assert edit_page.status_code == 200
        assert "Original notes" in edit_page.text

        response = client.post(
            f"/results/{result_id}",
            data={
                "member_id": str(member_id),
                "competition_id": str(competition_id),
                "style_subcategory_id": str(subcategory_id),
                "bjcp_score": "44.5",
                "place": "2",
                "placement_scope": PlacementScope.BEST_OF_SHOW.value,
                "recipe_url": "https://example.test/recipe",
                "notes": "Edited notes",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/results"
        with SessionLocal() as db:
            result = db.get(Result, result_id)
            assert result is not None
            assert result.bjcp_score == Decimal("44.5")
            assert result.place == 2
            assert result.placement_scope == PlacementScope.BEST_OF_SHOW
            assert result.recipe_url == "https://example.test/recipe"
            assert result.notes == "Edited notes"
    finally:
        cleanup_edit_data()
