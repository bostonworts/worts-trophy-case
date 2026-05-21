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
from app.services.uploads import delete_upload_url


TEST_COMPETITION_NAME = "__Attachment Competition__"
TEST_MEMBER_EMAIL = "attachment-member@example.test"
TEST_GUIDE_YEAR = 2096
TEST_CATEGORY_CODE = "U"
TEST_SUBCATEGORY_CODE = "U1"


def cleanup_attachment_data() -> None:
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


def create_attachment_records() -> tuple[int, int, int]:
    cleanup_attachment_data()
    with SessionLocal() as db:
        member = Member(email=TEST_MEMBER_EMAIL, display_name="Attachment Member")
        competition = Competition(
            name=TEST_COMPETITION_NAME,
            date=date(2026, 5, 18),
            competition_type=CompetitionType.BJCP_SANCTIONED,
        )
        category = StyleCategory(
            guide_year=TEST_GUIDE_YEAR,
            code=TEST_CATEGORY_CODE,
            name="Attachment Styles",
        )
        subcategory = StyleSubcategory(
            category=category,
            code=TEST_SUBCATEGORY_CODE,
            name="Attachment Style",
        )
        db.add_all([member, competition, subcategory])
        db.commit()
        return member.id, competition.id, subcategory.id


def test_result_can_upload_photo_and_recipe_file(admin_client) -> None:
    member_id, competition_id, subcategory_id = create_attachment_records()
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
                "recipe_url": "",
                "notes": "Attachment notes",
            },
            files={
                "photo": ("beer.png", b"fake image bytes", "image/png"),
                "recipe_file": ("recipe.pdf", b"%PDF-1.4 fake pdf", "application/pdf"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        with SessionLocal() as db:
            result = db.scalar(select(Result).where(Result.member_id == member_id))
            assert result is not None
            assert result.photo_url is not None
            assert result.recipe_file_url is not None
            assert result.photo_url.startswith(f"/uploads/results/{result.id}/photos/")
            assert result.recipe_file_url.startswith(f"/uploads/results/{result.id}/recipes/")

            photo_response = admin_client.get(result.photo_url)
            recipe_response = admin_client.get(result.recipe_file_url)
            assert photo_response.status_code == 200
            assert recipe_response.status_code == 200
            assert photo_response.headers["x-content-type-options"] == "nosniff"
            assert recipe_response.headers["content-disposition"] == "attachment"
            assert recipe_response.headers["x-content-type-options"] == "nosniff"
    finally:
        cleanup_attachment_data()


def test_result_attachment_upload_can_replace_and_remove(admin_client) -> None:
    member_id, competition_id, subcategory_id = create_attachment_records()
    try:
        create_response = admin_client.post(
            "/results",
            data={
                "member_id": str(member_id),
                "competition_id": str(competition_id),
                "style_subcategory_id": str(subcategory_id),
                "bjcp_score": "40.0",
                "place": "1",
                "placement_scope": PlacementScope.CATEGORY.value,
                "recipe_url": "",
                "notes": "",
            },
            files={
                "photo": ("beer.png", b"fake image bytes", "image/png"),
                "recipe_file": ("recipe.pdf", b"%PDF-1.4 fake pdf", "application/pdf"),
            },
            follow_redirects=False,
        )
        assert create_response.status_code == 303

        with SessionLocal() as db:
            result = db.scalar(select(Result).where(Result.member_id == member_id))
            assert result is not None
            result_id = result.id
            old_photo_url = result.photo_url
            old_recipe_file_url = result.recipe_file_url

        update_response = admin_client.post(
            f"/results/{result_id}",
            data={
                "member_id": str(member_id),
                "competition_id": str(competition_id),
                "style_subcategory_id": str(subcategory_id),
                "bjcp_score": "41.0",
                "place": "1",
                "placement_scope": PlacementScope.CATEGORY.value,
                "recipe_url": "",
                "notes": "",
                "remove_photo": "true",
            },
            files={
                "recipe_file": ("recipe-v2.pdf", b"%PDF-1.4 fake pdf v2", "application/pdf"),
            },
            follow_redirects=False,
        )

        assert update_response.status_code == 303
        with SessionLocal() as db:
            result = db.get(Result, result_id)
            assert result is not None
            assert result.bjcp_score == Decimal("41.0")
            assert result.photo_url is None
            assert result.recipe_file_url is not None
            assert result.recipe_file_url != old_recipe_file_url

            assert old_photo_url is not None
            assert old_recipe_file_url is not None
            assert admin_client.get(old_photo_url).status_code == 404
            assert admin_client.get(old_recipe_file_url).status_code == 404
            assert admin_client.get(result.recipe_file_url).status_code == 200
    finally:
        cleanup_attachment_data()


def test_result_rejects_unsupported_attachment(admin_client) -> None:
    member_id, competition_id, subcategory_id = create_attachment_records()
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
                "recipe_url": "",
                "notes": "",
            },
            files={
                "photo": ("not-a-photo.exe", b"fake binary", "application/octet-stream"),
            },
        )

        assert response.status_code == 400
        assert "Photos must be GIF, JPEG, PNG, or WebP files." in response.text
        with SessionLocal() as db:
            assert db.scalar(select(Result).where(Result.member_id == member_id)) is None
    finally:
        cleanup_attachment_data()


def test_result_rejects_active_recipe_attachment(admin_client) -> None:
    member_id, competition_id, subcategory_id = create_attachment_records()
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
                "recipe_url": "",
                "notes": "",
            },
            files={
                "recipe_file": ("recipe.html", b"<form></form>", "text/html"),
            },
        )

        assert response.status_code == 400
        assert "Recipe files must be PDF, text, Markdown, or JSON files." in response.text
        with SessionLocal() as db:
            assert db.scalar(select(Result).where(Result.member_id == member_id)) is None
    finally:
        cleanup_attachment_data()
