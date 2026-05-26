from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.auth import SESSION_COOKIE_NAME, session_token_for_member
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
from app.services.csrf import CSRF_COOKIE_NAME, csrf_token_from_signed_cookie


TEST_COMPETITION_NAME = "__Validation Competition__"
TEST_MEMBER_EMAIL = "validation-member@example.test"
TEST_GUIDE_YEAR = 2099
TEST_CATEGORY_CODE = "T"
TEST_SUBCATEGORY_CODE = "T1"


def cleanup_validation_data() -> None:
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


def create_validation_records() -> tuple[int, int, int]:
    cleanup_validation_data()
    with SessionLocal() as db:
        member = Member(email=TEST_MEMBER_EMAIL, display_name="Validation Member")
        competition = Competition(
            name=TEST_COMPETITION_NAME,
            date=date(2026, 5, 18),
            competition_type=CompetitionType.BJCP_SANCTIONED,
        )
        category = StyleCategory(
            guide_year=TEST_GUIDE_YEAR,
            code=TEST_CATEGORY_CODE,
            name="Validation Styles",
        )
        subcategory = StyleSubcategory(
            category=category,
            code=TEST_SUBCATEGORY_CODE,
            name="Validation Style",
        )
        db.add_all([member, competition, subcategory])
        db.commit()
        return member.id, competition.id, subcategory.id


def validation_member_client(member_id: int) -> TestClient:
    with SessionLocal() as db:
        member = db.get(Member, member_id)
        assert member is not None
        token = session_token_for_member(member)
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    client.get("/results")
    return client


def validation_csrf_token(client: TestClient) -> str:
    token = csrf_token_from_signed_cookie(client.cookies.get(CSRF_COOKIE_NAME))
    assert token is not None
    return token


def test_competition_create_requires_member_login() -> None:
    response = TestClient(app).get("/competitions/new", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/member-login?next=%2Fcompetitions%2Fnew"


def test_member_can_create_competition_without_admin_review() -> None:
    cleanup_validation_data()
    try:
        with SessionLocal() as db:
            member = Member(
                email=TEST_MEMBER_EMAIL,
                display_name="Validation Member",
                good_standing=True,
            )
            db.add(member)
            db.commit()
            member_id = member.id

        client = validation_member_client(member_id)
        form_response = client.get("/competitions/new")
        assert form_response.status_code == 200
        assert "Add competition" in form_response.text

        response = client.post(
            "/competitions",
            data={
                "name": TEST_COMPETITION_NAME,
                "date": "2026-05-18",
                "competition_type": CompetitionType.BJCP_SANCTIONED.value,
                "url": "https://example.test/competition",
                "csrf_token": validation_csrf_token(client),
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/competitions"
        with SessionLocal() as db:
            competition = db.scalar(
                select(Competition).where(Competition.name == TEST_COMPETITION_NAME)
            )
            assert competition is not None
            assert competition.url == "https://example.test/competition"
    finally:
        cleanup_validation_data()


def test_duplicate_competition_renders_validation_error(admin_client) -> None:
    cleanup_validation_data()
    try:
        with SessionLocal() as db:
            db.add(
                Competition(
                    name=TEST_COMPETITION_NAME,
                    date=date(2026, 5, 18),
                    competition_type=CompetitionType.BJCP_SANCTIONED,
                )
            )
            db.commit()

        client = admin_client
        response = client.post(
            "/competitions",
            data={
                "name": TEST_COMPETITION_NAME,
                "date": "2026-05-18",
                "competition_type": CompetitionType.BJCP_SANCTIONED.value,
                "url": "",
            },
        )

        assert response.status_code == 400
        assert "A competition with that name and date already exists." in response.text
        with SessionLocal() as db:
            count = db.scalar(
                select(func.count())
                .select_from(Competition)
                .where(Competition.name == TEST_COMPETITION_NAME)
            )
            assert count == 1
    finally:
        cleanup_validation_data()


def test_competition_rejects_non_http_url(admin_client) -> None:
    cleanup_validation_data()
    try:
        response = admin_client.post(
            "/competitions",
            data={
                "name": TEST_COMPETITION_NAME,
                "date": "2026-05-18",
                "competition_type": CompetitionType.BJCP_SANCTIONED.value,
                "url": "javascript:alert(1)",
            },
        )

        assert response.status_code == 400
        assert "Competition URL must be an http(s) URL." in response.text
        with SessionLocal() as db:
            assert (
                db.scalar(select(Competition).where(Competition.name == TEST_COMPETITION_NAME))
                is None
            )
    finally:
        cleanup_validation_data()


def test_result_requires_place_and_scope_together(admin_client) -> None:
    member_id, competition_id, subcategory_id = create_validation_records()
    try:
        client = admin_client
        response = client.post(
            "/results",
            data={
                "member_id": str(member_id),
                "competition_id": str(competition_id),
                "style_subcategory_id": str(subcategory_id),
                "bjcp_score": "42.0",
                "place": "1",
                "recipe_url": "",
                "notes": "",
            },
        )

        assert response.status_code == 400
        assert "Place and placement scope must be set together." in response.text
        with SessionLocal() as db:
            result = db.scalar(
                select(Result).where(
                    Result.member_id == member_id,
                    Result.competition_id == competition_id,
                    Result.style_subcategory_id == subcategory_id,
                )
            )
            assert result is None
    finally:
        cleanup_validation_data()


def test_result_form_has_searchable_selectors(admin_client) -> None:
    create_validation_records()
    try:
        response = admin_client.get("/results/new")

        assert response.status_code == 200
        assert 'data-controls="member_id"' in response.text
        assert 'data-controls="competition_id"' in response.text
        assert 'data-controls="style_subcategory_id"' in response.text
        assert 'id="member_filter_results"' in response.text
        assert 'id="competition_filter_results"' in response.text
        assert 'id="style_filter_results"' in response.text
        assert "maxChoiceMatches" in response.text
        assert "Choose member" in response.text
        assert "Choose competition" in response.text
        assert "Choose style" in response.text
    finally:
        cleanup_validation_data()


def test_result_requires_core_references(admin_client) -> None:
    cleanup_validation_data()
    try:
        response = admin_client.post(
            "/results",
            data={
                "bjcp_score": "42.0",
                "place": "",
                "placement_scope": "",
                "recipe_url": "",
                "notes": "",
            },
        )

        assert response.status_code == 400
        assert "Choose a member." in response.text
        assert "Choose a competition." in response.text
        assert "Choose a BJCP style." in response.text
    finally:
        cleanup_validation_data()


def test_result_rejects_out_of_range_score(admin_client) -> None:
    member_id, competition_id, subcategory_id = create_validation_records()
    try:
        client = admin_client
        response = client.post(
            "/results",
            data={
                "member_id": str(member_id),
                "competition_id": str(competition_id),
                "style_subcategory_id": str(subcategory_id),
                "bjcp_score": "0",
                "place": "1",
                "placement_scope": PlacementScope.CATEGORY.value,
                "recipe_url": "",
                "notes": "",
            },
        )

        assert response.status_code == 400
        assert "BJCP score must be greater than 0 and no more than 50." in response.text
        with SessionLocal() as db:
            result = db.scalar(
                select(Result).where(
                    Result.member_id == member_id,
                    Result.competition_id == competition_id,
                    Result.style_subcategory_id == subcategory_id,
                    Result.bjcp_score == Decimal("0"),
                )
            )
            assert result is None
    finally:
        cleanup_validation_data()


def test_result_rejects_unsafe_recipe_url(admin_client) -> None:
    member_id, competition_id, subcategory_id = create_validation_records()
    try:
        response = admin_client.post(
            "/results",
            data={
                "member_id": str(member_id),
                "competition_id": str(competition_id),
                "style_subcategory_id": str(subcategory_id),
                "bjcp_score": "40.0",
                "place": "1",
                "placement_scope": PlacementScope.CATEGORY.value,
                "recipe_url": "data:text/html,hello",
                "notes": "",
            },
        )

        assert response.status_code == 400
        assert "Recipe URL must be an http(s) URL." in response.text
        with SessionLocal() as db:
            assert db.scalar(select(Result).where(Result.member_id == member_id)) is None
    finally:
        cleanup_validation_data()
