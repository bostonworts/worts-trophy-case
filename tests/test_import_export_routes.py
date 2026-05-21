from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.db.models import (
    Competition,
    CompetitionType,
    Member,
    MemberEmail,
    MemberEmailKind,
    PlacementScope,
    Result,
    StyleCategory,
    StyleSubcategory,
)
from app.db.session import SessionLocal
from app.main import app


TEST_COMPETITION_NAME = "__Import Export Competition__"
TEST_EXISTING_COMPETITION_NAME = "__Import Existing Competition__"
TEST_NEW_COMPETITION_NAME = "__Import New Competition__"
TEST_ROLLBACK_COMPETITION_NAME = "__Import Rollback Competition__"
TEST_MEMBER_EMAIL = "import-export-member@example.test"
TEST_EXISTING_EMAIL = "import-existing@example.test"
TEST_NEW_EMAIL = "import-new@example.test"
TEST_ROLLBACK_EMAIL = "import-rollback@example.test"
TEST_PAYPAL_EMAIL = "import-paypal@example.test"
TEST_LIST_EMAIL = "import-list@example.test"
TEST_GUIDE_YEAR = 2092
TEST_CATEGORY_CODE = "77"
TEST_SUBCATEGORY_CODE = "77A"


def cleanup_import_export_data() -> None:
    with SessionLocal() as db:
        member_emails = [
            TEST_MEMBER_EMAIL,
            TEST_EXISTING_EMAIL,
            TEST_NEW_EMAIL,
            TEST_ROLLBACK_EMAIL,
            TEST_PAYPAL_EMAIL,
            TEST_LIST_EMAIL,
        ]
        competition_names = [
            TEST_COMPETITION_NAME,
            TEST_EXISTING_COMPETITION_NAME,
            TEST_NEW_COMPETITION_NAME,
            TEST_ROLLBACK_COMPETITION_NAME,
        ]
        competition_ids = list(
            db.scalars(select(Competition.id).where(Competition.name.in_(competition_names)))
        )
        member_ids = list(db.scalars(select(Member.id).where(Member.email.in_(member_emails))))
        alias_member_ids = list(
            db.scalars(select(MemberEmail.member_id).where(MemberEmail.email.in_(member_emails)))
        )
        member_ids.extend(alias_member_ids)
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


def create_export_result() -> int:
    cleanup_import_export_data()
    with SessionLocal() as db:
        member = Member(email=TEST_MEMBER_EMAIL, display_name="Import Export Member")
        competition = Competition(
            name=TEST_COMPETITION_NAME,
            date=date(2026, 5, 18),
            competition_type=CompetitionType.BJCP_SANCTIONED,
        )
        category = StyleCategory(
            guide_year=TEST_GUIDE_YEAR,
            code=TEST_CATEGORY_CODE,
            name="Import Export Category",
        )
        subcategory = StyleSubcategory(
            category=category,
            code=TEST_SUBCATEGORY_CODE,
            name="Import Export Style",
        )
        result = Result(
            member=member,
            competition=competition,
            style_subcategory=subcategory,
            bjcp_score=Decimal("44.0"),
            place=1,
            placement_scope=PlacementScope.CATEGORY,
            notes="Export notes",
        )
        db.add(result)
        db.commit()
        return result.id


def create_result_import_refs() -> tuple[int, int, int]:
    cleanup_import_export_data()
    with SessionLocal() as db:
        member = Member(email=TEST_MEMBER_EMAIL, display_name="Import Export Member")
        competition = Competition(
            name=TEST_COMPETITION_NAME,
            date=date(2026, 5, 18),
            competition_type=CompetitionType.BJCP_SANCTIONED,
        )
        category = StyleCategory(
            guide_year=TEST_GUIDE_YEAR,
            code=TEST_CATEGORY_CODE,
            name="Import Export Category",
        )
        subcategory = StyleSubcategory(
            category=category,
            code=TEST_SUBCATEGORY_CODE,
            name="Import Export Style",
        )
        db.add_all([member, competition, subcategory])
        db.commit()
        return member.id, competition.id, subcategory.id


def test_member_csv_export_requires_admin_and_contains_members(admin_client) -> None:
    cleanup_import_export_data()
    try:
        with SessionLocal() as db:
            db.add(Member(email=TEST_MEMBER_EMAIL, display_name="Import Export Member"))
            db.commit()

        public_response = TestClient(app).get("/members.csv", follow_redirects=False)
        admin_response = admin_client.get("/members.csv")

        assert public_response.status_code == 303
        assert public_response.headers["location"].startswith("/login")
        assert admin_response.status_code == 200
        assert admin_response.headers["content-disposition"] == 'attachment; filename="members.csv"'
        assert "email,paypal_email,mailing_list_email,display_name" in admin_response.text
        assert TEST_MEMBER_EMAIL in admin_response.text
    finally:
        cleanup_import_export_data()


def test_result_csv_export_contains_result_context(admin_client) -> None:
    result_id = create_export_result()
    try:
        response = admin_client.get("/results.csv")

        assert response.status_code == 200
        assert response.headers["content-disposition"] == 'attachment; filename="results.csv"'
        assert "member_email,member_display_name,competition_name" in response.text
        assert str(result_id) in response.text
        assert TEST_MEMBER_EMAIL in response.text
        assert TEST_COMPETITION_NAME in response.text
        assert TEST_SUBCATEGORY_CODE in response.text
        assert "44.0" in response.text
        assert "3" in response.text
        assert "Export notes" in response.text
    finally:
        cleanup_import_export_data()


def test_competition_csv_export_requires_admin_and_contains_competitions(admin_client) -> None:
    cleanup_import_export_data()
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

        public_response = TestClient(app).get("/competitions.csv", follow_redirects=False)
        admin_response = admin_client.get("/competitions.csv")

        assert public_response.status_code == 303
        assert public_response.headers["location"].startswith("/login")
        assert admin_response.status_code == 200
        assert admin_response.headers["content-disposition"] == (
            'attachment; filename="competitions.csv"'
        )
        assert "name,date,competition_type,url,status" in admin_response.text
        assert TEST_COMPETITION_NAME in admin_response.text
        assert CompetitionType.BJCP_SANCTIONED.value in admin_response.text
    finally:
        cleanup_import_export_data()


def test_member_csv_import_creates_updates_and_deactivates(admin_client) -> None:
    cleanup_import_export_data()
    try:
        with SessionLocal() as db:
            db.add(Member(email=TEST_EXISTING_EMAIL, display_name="Existing Member", is_admin=True))
            db.commit()

        csv_body = (
            "email,display_name,is_admin,status\n"
            f"{TEST_NEW_EMAIL},Imported New,true,active\n"
            f"{TEST_EXISTING_EMAIL},Existing Updated,false,inactive\n"
        )
        response = admin_client.post(
            "/members/import",
            files={"csv_file": ("members.csv", csv_body.encode(), "text/csv")},
        )

        assert response.status_code == 200
        assert "Imported 2 members from CSV: 1 created, 1 updated." in response.text
        with SessionLocal() as db:
            new_member = db.scalar(select(Member).where(Member.email == TEST_NEW_EMAIL))
            existing_member = db.scalar(select(Member).where(Member.email == TEST_EXISTING_EMAIL))
            assert new_member is not None
            assert new_member.display_name == "Imported New"
            assert new_member.is_admin
            assert new_member.deactivated_at is None
            assert existing_member is not None
            assert existing_member.display_name == "Existing Updated"
            assert not existing_member.is_admin
            assert existing_member.deactivated_at is not None
    finally:
        cleanup_import_export_data()


def test_member_csv_import_accepts_roster_columns(admin_client) -> None:
    cleanup_import_export_data()
    try:
        csv_body = (
            "member,name,paypal_email,list_email\n"
            f"1,Roster Member,{TEST_PAYPAL_EMAIL},{TEST_LIST_EMAIL}\n"
        )
        response = admin_client.post(
            "/members/import",
            files={"csv_file": ("members.csv", csv_body.encode(), "text/csv")},
        )

        assert response.status_code == 200
        assert "Imported 1 members from CSV: 1 created, 0 updated." in response.text
        with SessionLocal() as db:
            member = db.scalar(select(Member).where(Member.email == TEST_LIST_EMAIL))
            assert member is not None
            assert member.display_name == "Roster Member"
            assert member.good_standing
            aliases = {
                alias.kind: alias.email
                for alias in db.scalars(
                    select(MemberEmail).where(MemberEmail.member_id == member.id)
                )
            }
            assert aliases[MemberEmailKind.PAYPAL] == TEST_PAYPAL_EMAIL
            assert member.email == TEST_LIST_EMAIL
    finally:
        cleanup_import_export_data()


def test_member_import_accepts_google_sheet_url(admin_client, monkeypatch) -> None:
    cleanup_import_export_data()
    csv_body = (
        "Member,Name,PayPal Email,List Email\n"
        f"1,Google Sheet Member,{TEST_PAYPAL_EMAIL},{TEST_LIST_EMAIL}\n"
    )
    fetched_urls = []

    def fake_fetch(url: str) -> bytes:
        fetched_urls.append(url)
        return csv_body.encode()

    monkeypatch.setattr("app.routers.members.fetch_google_sheet_csv", fake_fetch)
    try:
        response = admin_client.post(
            "/members/import",
            data={
                "google_sheet_url": (
                    "https://docs.google.com/spreadsheets/d/sheet-id/edit#gid=123"
                )
            },
        )

        assert response.status_code == 200
        assert fetched_urls == ["https://docs.google.com/spreadsheets/d/sheet-id/edit#gid=123"]
        assert "Imported 1 members from Google Sheets: 1 created, 0 updated." in response.text
        with SessionLocal() as db:
            member = db.scalar(select(Member).where(Member.email == TEST_LIST_EMAIL))
            assert member is not None
            assert member.display_name == "Google Sheet Member"
            assert member.good_standing
    finally:
        cleanup_import_export_data()


def test_member_csv_import_preview_does_not_write(admin_client) -> None:
    cleanup_import_export_data()
    try:
        with SessionLocal() as db:
            db.add(Member(email=TEST_EXISTING_EMAIL, display_name="Existing Member"))
            db.commit()

        csv_body = (
            "email,display_name,is_admin,status\n"
            f"{TEST_NEW_EMAIL},Imported New,true,active\n"
            f"{TEST_EXISTING_EMAIL},Existing Updated,false,inactive\n"
        )
        response = admin_client.post(
            "/members/import",
            data={"action": "preview"},
            files={"csv_file": ("members.csv", csv_body.encode(), "text/csv")},
        )

        assert response.status_code == 200
        assert "Previewed 2 members: 1 create, 1 update, 0 skip." in response.text
        with SessionLocal() as db:
            assert db.scalar(select(Member).where(Member.email == TEST_NEW_EMAIL)) is None
            existing_member = db.scalar(select(Member).where(Member.email == TEST_EXISTING_EMAIL))
            assert existing_member is not None
            assert existing_member.display_name == "Existing Member"
            assert existing_member.deactivated_at is None
    finally:
        cleanup_import_export_data()


def test_result_csv_import_creates_results(admin_client) -> None:
    member_id, competition_id, subcategory_id = create_result_import_refs()
    try:
        csv_body = (
            "member_email,competition_name,competition_date,style_guide_year,"
            "style_subcategory_code,bjcp_score,place,placement_scope,recipe_url,notes,"
            "result_status\n"
            f"{TEST_MEMBER_EMAIL},{TEST_COMPETITION_NAME},2026-05-18,{TEST_GUIDE_YEAR},"
            f"{TEST_SUBCATEGORY_CODE},44.5,1,category,https://example.test/recipe,"
            "Imported result,active\n"
            f"{TEST_MEMBER_EMAIL},{TEST_COMPETITION_NAME},2026-05-18,{TEST_GUIDE_YEAR},"
            f"{TEST_SUBCATEGORY_CODE},,,,"
            ",Archived import,archived\n"
        )
        response = admin_client.post(
            "/results/import",
            files={"csv_file": ("results.csv", csv_body.encode(), "text/csv")},
        )

        assert response.status_code == 200
        assert "Imported 2 results." in response.text
        with SessionLocal() as db:
            results = list(
                db.scalars(select(Result).where(Result.member_id == member_id).order_by(Result.id))
            )
            assert len(results) == 2
            active_result = results[0]
            archived_result = results[1]
            assert active_result.competition_id == competition_id
            assert active_result.style_subcategory_id == subcategory_id
            assert active_result.bjcp_score == Decimal("44.5")
            assert active_result.place == 1
            assert active_result.placement_scope == PlacementScope.CATEGORY
            assert active_result.recipe_url == "https://example.test/recipe"
            assert active_result.notes == "Imported result"
            assert active_result.archived_at is None
            assert archived_result.notes == "Archived import"
            assert archived_result.archived_at is not None
    finally:
        cleanup_import_export_data()


def test_result_csv_import_preview_and_skips_likely_duplicates(admin_client) -> None:
    member_id, competition_id, subcategory_id = create_result_import_refs()
    try:
        with SessionLocal() as db:
            db.add(
                Result(
                    member_id=member_id,
                    competition_id=competition_id,
                    style_subcategory_id=subcategory_id,
                    bjcp_score=Decimal("44.5"),
                    place=1,
                    placement_scope=PlacementScope.CATEGORY,
                    notes="Existing result",
                )
            )
            db.commit()

        csv_body = (
            "member_email,competition_name,competition_date,style_guide_year,"
            "style_subcategory_code,bjcp_score,place,placement_scope,notes\n"
            f"{TEST_MEMBER_EMAIL},{TEST_COMPETITION_NAME},2026-05-18,{TEST_GUIDE_YEAR},"
            f"{TEST_SUBCATEGORY_CODE},44.5,1,category,Duplicate result\n"
            f"{TEST_MEMBER_EMAIL},{TEST_COMPETITION_NAME},2026-05-18,{TEST_GUIDE_YEAR},"
            f"{TEST_SUBCATEGORY_CODE},42.0,2,category,Fresh result\n"
        )
        preview_response = admin_client.post(
            "/results/import",
            data={"action": "preview"},
            files={"csv_file": ("results.csv", csv_body.encode(), "text/csv")},
        )

        assert preview_response.status_code == 200
        assert "Previewed 2 results: 1 create, 0 update, 1 skip." in preview_response.text
        assert "likely duplicate of an existing result" in preview_response.text
        with SessionLocal() as db:
            result_count = db.scalar(
                select(func.count(Result.id)).where(Result.member_id == member_id)
            )
            assert result_count == 1

        import_response = admin_client.post(
            "/results/import",
            files={"csv_file": ("results.csv", csv_body.encode(), "text/csv")},
        )

        assert import_response.status_code == 200
        assert "Imported 1 results. Skipped 1 likely duplicates." in import_response.text
        with SessionLocal() as db:
            result_count = db.scalar(
                select(func.count(Result.id)).where(Result.member_id == member_id)
            )
            assert result_count == 2
    finally:
        cleanup_import_export_data()


def test_result_csv_import_accepts_export_columns(admin_client) -> None:
    member_id, _, _ = create_result_import_refs()
    try:
        csv_body = (
            "id,member_email,member_display_name,competition_name,competition_date,"
            "competition_type,style_category_code,style_category_name,style_subcategory_code,"
            "style_subcategory_name,bjcp_score,place,placement_scope,leaderboard_points,"
            "recipe_url,recipe_file_url,photo_url,notes,result_archived_at,"
            "competition_archived_at,created_at,updated_at\n"
            f"999,{TEST_MEMBER_EMAIL},Import Export Member,{TEST_COMPETITION_NAME},"
            f"2026-05-18,{CompetitionType.BJCP_SANCTIONED.value},{TEST_CATEGORY_CODE},"
            f"Import Export Category,{TEST_SUBCATEGORY_CODE},Import Export Style,42.0,2,"
            "category,2,https://example.test/recipe,/uploads/recipe.pdf,/uploads/photo.png,"
            "Export shaped import,,,,\n"
        )
        response = admin_client.post(
            "/results/import",
            files={"csv_file": ("results.csv", csv_body.encode(), "text/csv")},
        )

        assert response.status_code == 200
        with SessionLocal() as db:
            result = db.scalar(select(Result).where(Result.member_id == member_id))
            assert result is not None
            assert result.bjcp_score == Decimal("42.0")
            assert result.place == 2
            assert result.recipe_file_url == "/uploads/recipe.pdf"
            assert result.photo_url == "/uploads/photo.png"
            assert result.notes == "Export shaped import"
    finally:
        cleanup_import_export_data()


def test_result_csv_import_rejects_unresolved_references_without_partial_write(
    admin_client,
) -> None:
    member_id, _, _ = create_result_import_refs()
    try:
        csv_body = (
            "member_email,competition_name,competition_date,style_guide_year,"
            "style_subcategory_code,bjcp_score,place,placement_scope,notes\n"
            f"{TEST_MEMBER_EMAIL},{TEST_COMPETITION_NAME},2026-05-18,{TEST_GUIDE_YEAR},"
            f"{TEST_SUBCATEGORY_CODE},40.0,1,category,Should rollback\n"
            f"missing@example.test,{TEST_COMPETITION_NAME},2026-05-18,{TEST_GUIDE_YEAR},"
            "NOPE,90.0,5,category,Bad row\n"
        )
        response = admin_client.post(
            "/results/import",
            files={"csv_file": ("results.csv", csv_body.encode(), "text/csv")},
        )

        assert response.status_code == 400
        assert "Row 3: member_email missing@example.test was not found." in response.text
        assert "Row 3: style_subcategory_code NOPE" in response.text
        assert "Row 3: bjcp_score must be greater than 0 and no more than 50." in response.text
        assert "Row 3: place must be 1st, 2nd, 3rd, or HM." in response.text
        with SessionLocal() as db:
            assert db.scalar(select(Result).where(Result.member_id == member_id)) is None
    finally:
        cleanup_import_export_data()


def test_result_csv_import_resolves_missing_references(admin_client) -> None:
    cleanup_import_export_data()
    try:
        csv_body = (
            "member_email,member_display_name,competition_name,competition_date,"
            "competition_type,style_guide_year,style_category_code,style_category_name,"
            "style_subcategory_code,style_subcategory_name,bjcp_score,place,"
            "placement_scope,notes\n"
            f"{TEST_NEW_EMAIL},Resolved Member,{TEST_NEW_COMPETITION_NAME},2026-06-01,"
            f"{CompetitionType.BJCP_SANCTIONED.value},{TEST_GUIDE_YEAR},"
            f"{TEST_CATEGORY_CODE},Resolved Category,{TEST_SUBCATEGORY_CODE},"
            "Resolved Style,41.0,1,category,Resolved import\n"
        )
        response = admin_client.post(
            "/results/import",
            data={"action": "resolve"},
            files={"csv_file": ("results.csv", csv_body.encode(), "text/csv")},
        )

        assert response.status_code == 200
        assert "Resolved 1 members, 1 competitions, and 1 styles." in response.text
        with SessionLocal() as db:
            member = db.scalar(select(Member).where(Member.email == TEST_NEW_EMAIL))
            competition = db.scalar(
                select(Competition).where(Competition.name == TEST_NEW_COMPETITION_NAME)
            )
            result = db.scalar(
                select(Result).join(Result.member).where(Member.email == TEST_NEW_EMAIL)
            )
            assert member is not None
            assert member.display_name == "Resolved Member"
            assert competition is not None
            assert result is not None
            assert result.notes == "Resolved import"
    finally:
        cleanup_import_export_data()


def test_competition_csv_import_creates_updates_and_archives(admin_client) -> None:
    cleanup_import_export_data()
    try:
        with SessionLocal() as db:
            db.add(
                Competition(
                    name=TEST_EXISTING_COMPETITION_NAME,
                    date=date(2026, 5, 18),
                    competition_type=CompetitionType.OTHER,
                    url="https://example.test/old",
                )
            )
            db.commit()

        csv_body = (
            "name,date,competition_type,url,status\n"
            f"{TEST_NEW_COMPETITION_NAME},2026-06-01,"
            f"{CompetitionType.CLUB_ONLY.value},https://example.test/new,active\n"
            f"{TEST_EXISTING_COMPETITION_NAME},2026-05-18,"
            f"{CompetitionType.BJCP_SANCTIONED.value},https://example.test/updated,archived\n"
        )
        response = admin_client.post(
            "/competitions/import",
            files={"csv_file": ("competitions.csv", csv_body.encode(), "text/csv")},
        )

        assert response.status_code == 200
        assert "Imported 2 competitions: 1 created, 1 updated." in response.text
        with SessionLocal() as db:
            new_competition = db.scalar(
                select(Competition).where(Competition.name == TEST_NEW_COMPETITION_NAME)
            )
            existing_competition = db.scalar(
                select(Competition).where(Competition.name == TEST_EXISTING_COMPETITION_NAME)
            )
            assert new_competition is not None
            assert new_competition.competition_type == CompetitionType.CLUB_ONLY
            assert new_competition.url == "https://example.test/new"
            assert new_competition.archived_at is None
            assert existing_competition is not None
            assert existing_competition.competition_type == CompetitionType.BJCP_SANCTIONED
            assert existing_competition.url == "https://example.test/updated"
            assert existing_competition.archived_at is not None
    finally:
        cleanup_import_export_data()


def test_competition_csv_import_preview_does_not_write(admin_client) -> None:
    cleanup_import_export_data()
    try:
        with SessionLocal() as db:
            db.add(
                Competition(
                    name=TEST_EXISTING_COMPETITION_NAME,
                    date=date(2026, 5, 18),
                    competition_type=CompetitionType.OTHER,
                )
            )
            db.commit()

        csv_body = (
            "name,date,competition_type,url,status\n"
            f"{TEST_NEW_COMPETITION_NAME},2026-06-01,"
            f"{CompetitionType.CLUB_ONLY.value},https://example.test/new,active\n"
            f"{TEST_EXISTING_COMPETITION_NAME},2026-05-18,"
            f"{CompetitionType.BJCP_SANCTIONED.value},https://example.test/updated,archived\n"
        )
        response = admin_client.post(
            "/competitions/import",
            data={"action": "preview"},
            files={"csv_file": ("competitions.csv", csv_body.encode(), "text/csv")},
        )

        assert response.status_code == 200
        assert "Previewed 2 competitions: 1 create, 1 update, 0 skip." in response.text
        with SessionLocal() as db:
            assert (
                db.scalar(
                    select(Competition).where(Competition.name == TEST_NEW_COMPETITION_NAME)
                )
                is None
            )
            existing_competition = db.scalar(
                select(Competition).where(Competition.name == TEST_EXISTING_COMPETITION_NAME)
            )
            assert existing_competition is not None
            assert existing_competition.competition_type == CompetitionType.OTHER
            assert existing_competition.archived_at is None
    finally:
        cleanup_import_export_data()


def test_competition_csv_import_rejects_errors_without_partial_write(admin_client) -> None:
    cleanup_import_export_data()
    try:
        csv_body = (
            "name,date,competition_type,url,status\n"
            f"{TEST_ROLLBACK_COMPETITION_NAME},2026-06-01,"
            f"{CompetitionType.CLUB_ONLY.value},,active\n"
            ",not-a-date,unknown,,retired\n"
        )
        response = admin_client.post(
            "/competitions/import",
            files={"csv_file": ("competitions.csv", csv_body.encode(), "text/csv")},
        )

        assert response.status_code == 400
        assert "Row 3: name is required." in response.text
        assert "Row 3: date must be YYYY-MM-DD." in response.text
        assert "Row 3: competition_type is invalid." in response.text
        assert "Row 3: status must be active or archived." in response.text
        with SessionLocal() as db:
            assert (
                db.scalar(
                    select(Competition).where(
                        Competition.name == TEST_ROLLBACK_COMPETITION_NAME
                    )
                )
                is None
            )
    finally:
        cleanup_import_export_data()


def test_member_csv_import_rejects_errors_without_partial_write(admin_client) -> None:
    cleanup_import_export_data()
    try:
        csv_body = (
            "email,display_name,is_admin,status\n"
            f"{TEST_ROLLBACK_EMAIL},Rollback Member,false,active\n"
            "bad-email,,maybe,retired\n"
        )
        response = admin_client.post(
            "/members/import",
            files={"csv_file": ("members.csv", csv_body.encode(), "text/csv")},
        )

        assert response.status_code == 400
        assert "Row 3: email must look like an email address." in response.text
        assert "Row 3: display_name is required." in response.text
        assert "Row 3: is_admin must be true or false." in response.text
        assert "Row 3: status must be active or inactive." in response.text
        with SessionLocal() as db:
            assert db.scalar(select(Member).where(Member.email == TEST_ROLLBACK_EMAIL)) is None
    finally:
        cleanup_import_export_data()
