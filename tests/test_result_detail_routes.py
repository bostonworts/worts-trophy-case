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


TEST_COMPETITION_NAME = "__Detail Competition__"
TEST_MEMBER_EMAIL = "detail-member@example.test"
TEST_GUIDE_YEAR = 2095
TEST_CATEGORY_CODE = "D"
TEST_SUBCATEGORY_CODE = "D1"


def cleanup_detail_data() -> None:
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


def create_detail_result(
    *,
    archived_result: bool = False,
    archived_competition: bool = False,
) -> int:
    cleanup_detail_data()
    archived_at = datetime.now(UTC)
    with SessionLocal() as db:
        member = Member(email=TEST_MEMBER_EMAIL, display_name="Detail Member")
        competition = Competition(
            name=TEST_COMPETITION_NAME,
            date=date(2026, 5, 18),
            competition_type=CompetitionType.BJCP_SANCTIONED,
            url="https://example.test/competition",
            archived_at=archived_at if archived_competition else None,
        )
        category = StyleCategory(
            guide_year=TEST_GUIDE_YEAR,
            code=TEST_CATEGORY_CODE,
            name="Detail Styles",
        )
        subcategory = StyleSubcategory(
            category=category,
            code=TEST_SUBCATEGORY_CODE,
            name="Detail Style",
        )
        result = Result(
            member=member,
            competition=competition,
            style_subcategory=subcategory,
            bjcp_score=Decimal("41.5"),
            place=1,
            placement_scope=PlacementScope.CATEGORY,
            recipe_url="https://example.test/detail-recipe",
            recipe_file_url="/uploads/detail/recipe.pdf",
            photo_url="/uploads/detail/photo.png",
            notes="Detail notes",
            archived_at=archived_at if archived_result else None,
        )
        db.add(result)
        db.commit()
        return result.id


def test_public_can_view_active_result_detail() -> None:
    result_id = create_detail_result()
    try:
        client = TestClient(app)

        response = client.get(f"/results/{result_id}")

        assert response.status_code == 200
        assert "Detail Member" in response.text
        assert TEST_COMPETITION_NAME in response.text
        assert "D1 Detail Style" in response.text
        assert "Detail notes" in response.text
        assert "41.5" in response.text
        assert ">3</dd>" in response.text
        assert 'href="https://example.test/detail-recipe"' in response.text
        assert 'href="/uploads/detail/recipe.pdf"' in response.text
        assert 'src="/uploads/detail/photo.png"' in response.text

        index_response = client.get("/results")
        assert index_response.status_code == 200
        assert f'href="/results/{result_id}"' in index_response.text
    finally:
        cleanup_detail_data()


def test_results_can_filter_by_season_category_and_placement() -> None:
    result_id = create_detail_result()
    try:
        with SessionLocal() as db:
            result = db.get(Result, result_id)
            assert result is not None
            member_id = result.member_id
            category_id = result.style_subcategory.category_id

        client = TestClient(app)

        matching_response = client.get(
            f"/results?season=2025-2026&member_id={member_id}"
            f"&category_id={category_id}&placement=placed"
        )
        placement_response = client.get("/results?placement=unplaced")
        season_response = client.get(f"/results?season=2026-2027&category_id={category_id}")

        assert matching_response.status_code == 200
        assert "Detail Member" in matching_response.text
        assert f'href="/results/{result_id}"' in matching_response.text
        assert "D1 Detail Style" in matching_response.text
        assert placement_response.status_code == 200
        assert f'href="/results/{result_id}"' not in placement_response.text
        assert "No results match those filters." in placement_response.text
        assert season_response.status_code == 200
        assert f'href="/results/{result_id}"' not in season_response.text
    finally:
        cleanup_detail_data()


def test_results_search_form_accepts_blank_dropdown_values() -> None:
    result_id = create_detail_result()
    try:
        response = TestClient(app).get(
            "/results",
            params={
                "q": "",
                "season": "",
                "member_id": "",
                "competition_id": "",
                "category_id": "",
                "placement": "",
            },
        )

        assert response.status_code == 200
        assert 'data-autosubmit' in response.text
        assert "trophyCase.results.keywordFocus" in response.text
        assert "setSelectionRange" in response.text
        assert 'onchange="this.form.submit()"' in response.text
        assert "Apply filters" not in response.text
        assert "Reset filters" not in response.text
        assert f'href="/results/{result_id}"' in response.text
    finally:
        cleanup_detail_data()


def test_public_cannot_view_archived_result_but_admin_can(admin_client) -> None:
    result_id = create_detail_result(archived_result=True)
    try:
        public_response = TestClient(app).get(f"/results/{result_id}")
        admin_response = admin_client.get(f"/results/{result_id}")

        assert public_response.status_code == 404
        assert admin_response.status_code == 200
        assert "This result is archived." in admin_response.text
        assert "Detail Member" in admin_response.text
    finally:
        cleanup_detail_data()


def test_public_cannot_view_result_for_archived_competition(admin_client) -> None:
    result_id = create_detail_result(archived_competition=True)
    try:
        public_response = TestClient(app).get(f"/results/{result_id}")
        admin_response = admin_client.get(f"/results/{result_id}")

        assert public_response.status_code == 404
        assert admin_response.status_code == 200
        assert "This result is hidden because its competition is archived." in admin_response.text
        assert TEST_COMPETITION_NAME in admin_response.text
    finally:
        cleanup_detail_data()


def test_admin_results_list_includes_results_from_archived_competitions(admin_client) -> None:
    result_id = create_detail_result(archived_competition=True)
    try:
        public_response = TestClient(app).get("/results")
        admin_response = admin_client.get("/results")

        assert public_response.status_code == 200
        assert f'href="/results/{result_id}"' not in public_response.text
        assert admin_response.status_code == 200
        assert "Archived results" in admin_response.text
        assert "Competition " in admin_response.text
        assert f'href="/results/{result_id}"' in admin_response.text
    finally:
        cleanup_detail_data()
