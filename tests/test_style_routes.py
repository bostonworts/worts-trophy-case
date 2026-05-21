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


TEST_COMPETITION_NAME = "__Style Route Competition__"
TEST_MEMBER_EMAIL = "style-route-member@example.test"
TEST_GUIDE_YEAR = 2093
TEST_CATEGORY_CODE = "88"
TEST_SUBCATEGORY_CODE = "88A"


def cleanup_style_route_data() -> None:
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


def create_style_route_result(*, archived_result: bool = False) -> tuple[int, int, int, int]:
    cleanup_style_route_data()
    with SessionLocal() as db:
        member = Member(email=TEST_MEMBER_EMAIL, display_name="Style Route Member")
        competition = Competition(
            name=TEST_COMPETITION_NAME,
            date=date(2026, 5, 18),
            competition_type=CompetitionType.BJCP_SANCTIONED,
        )
        category = StyleCategory(
            guide_year=TEST_GUIDE_YEAR,
            code=TEST_CATEGORY_CODE,
            name="Style Route Category",
        )
        subcategory = StyleSubcategory(
            category=category,
            code=TEST_SUBCATEGORY_CODE,
            name="Style Route Subcategory",
        )
        result = Result(
            member=member,
            competition=competition,
            style_subcategory=subcategory,
            bjcp_score=Decimal("43.0"),
            place=1,
            placement_scope=PlacementScope.CATEGORY,
            archived_at=datetime.now(UTC) if archived_result else None,
        )
        db.add(result)
        db.commit()
        return category.id, subcategory.id, member.id, result.id


def test_public_style_pages_show_active_results() -> None:
    category_id, subcategory_id, member_id, result_id = create_style_route_result()
    try:
        client = TestClient(app)

        index_response = client.get("/styles")
        category_response = client.get(f"/styles/{category_id}")
        subcategory_response = client.get(f"/styles/subcategories/{subcategory_id}")

        assert index_response.status_code == 200
        assert "Style Route Category" in index_response.text
        assert f'href="/styles/{category_id}"' in index_response.text
        assert category_response.status_code == 200
        assert "88A" in category_response.text
        assert "Style Route Member" in category_response.text
        assert f'href="/styles/subcategories/{subcategory_id}"' in category_response.text
        assert f'href="/results?category_id={category_id}"' in category_response.text
        assert subcategory_response.status_code == 200
        assert "43.0" in subcategory_response.text
        assert "3 leaderboard points" in subcategory_response.text
        assert f'href="/members/{member_id}"' in subcategory_response.text
        assert f'href="/results/{result_id}"' in subcategory_response.text
        assert f'href="/results?style_subcategory_id={subcategory_id}"' in subcategory_response.text
    finally:
        cleanup_style_route_data()


def test_results_archive_can_search_and_filter_by_subcategory() -> None:
    _, subcategory_id, _, result_id = create_style_route_result()
    try:
        client = TestClient(app)

        search_response = client.get("/results?q=Style+Route")
        subcategory_response = client.get(f"/results?style_subcategory_id={subcategory_id}")
        miss_response = client.get("/results?q=NotAStyleRouteMatch")

        assert search_response.status_code == 200
        assert f'href="/results/{result_id}"' in search_response.text
        assert subcategory_response.status_code == 200
        assert f'href="/results/{result_id}"' in subcategory_response.text
        assert miss_response.status_code == 200
        assert f'href="/results/{result_id}"' not in miss_response.text
        assert "No results match those filters." in miss_response.text
    finally:
        cleanup_style_route_data()


def test_admin_style_page_shows_hidden_results(admin_client) -> None:
    category_id, subcategory_id, _, result_id = create_style_route_result(archived_result=True)
    try:
        public_response = TestClient(app).get(f"/styles/{category_id}")
        admin_response = admin_client.get(f"/styles/subcategories/{subcategory_id}")

        assert public_response.status_code == 200
        assert f'href="/results/{result_id}"' not in public_response.text
        assert "No public results for this category." in public_response.text
        assert admin_response.status_code == 200
        assert "Hidden results" in admin_response.text
        assert "Result archived" in admin_response.text
        assert f'href="/results/{result_id}"' in admin_response.text
        assert "Style Route Member" in admin_response.text
    finally:
        cleanup_style_route_data()
