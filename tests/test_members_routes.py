from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.db.models import AuditLog, Member, MemberEmail, MemberEmailKind, Result
from app.db.session import SessionLocal


ADMIN_EMAIL = "test-admin@example.test"
TEST_EMAIL = "route-member@example.test"
TEST_EMAIL_2 = "route-member-2@example.test"
PAYPAL_EMAIL = "route-paypal@example.test"
PAYPAL_EMAIL_2 = "route-paypal-2@example.test"
LIST_EMAIL = "route-list@example.test"
LIST_EMAIL_2 = "route-list-2@example.test"


def cleanup_member() -> None:
    with SessionLocal() as db:
        member_ids = list(
            db.scalars(
                select(Member.id).where(
                    Member.email.in_(
                        [
                            TEST_EMAIL,
                            TEST_EMAIL_2,
                            PAYPAL_EMAIL,
                            PAYPAL_EMAIL_2,
                            LIST_EMAIL,
                            LIST_EMAIL_2,
                        ]
                    )
                )
            )
        )
        alias_member_ids = list(
            db.scalars(
                select(MemberEmail.member_id).where(
                    MemberEmail.email.in_(
                        [
                            TEST_EMAIL,
                            TEST_EMAIL_2,
                            PAYPAL_EMAIL,
                            PAYPAL_EMAIL_2,
                            LIST_EMAIL,
                            LIST_EMAIL_2,
                        ]
                    )
                )
            )
        )
        member_ids.extend(alias_member_ids)
        if member_ids:
            db.execute(delete(Result).where(Result.member_id.in_(member_ids)))
            db.execute(delete(AuditLog).where(AuditLog.actor_member_id.in_(member_ids)))
            db.execute(delete(Member).where(Member.id.in_(member_ids)))
            db.commit()


def test_member_can_be_created_and_listed(admin_client) -> None:
    cleanup_member()
    try:
        client = admin_client

        response = client.post(
            "/members",
            data={
                "display_name": " Route Member ",
                "email": " ROUTE-MEMBER@EXAMPLE.TEST ",
                "paypal_email": f" {PAYPAL_EMAIL.upper()} ",
                "mailing_list_email": f" {LIST_EMAIL.upper()} ",
                "good_standing": "true",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/members"

        index = client.get("/members")
        assert index.status_code == 200
        assert "Route Member" in index.text
        assert TEST_EMAIL in index.text
        assert PAYPAL_EMAIL in index.text
        assert LIST_EMAIL in index.text

        with SessionLocal() as db:
            member = db.scalar(select(Member).where(Member.email == TEST_EMAIL))
            assert member is not None
            assert member.display_name == "Route Member"
            assert not member.is_admin
            assert member.good_standing
            assert member.submission_review_required
            aliases = {
                alias.kind: alias.email
                for alias in db.scalars(
                    select(MemberEmail).where(MemberEmail.member_id == member.id)
                )
            }
            assert aliases[MemberEmailKind.PAYPAL] == PAYPAL_EMAIL
            assert aliases[MemberEmailKind.MAILING_LIST] == LIST_EMAIL
    finally:
        cleanup_member()


def test_member_submission_review_requirement_can_be_removed(admin_client) -> None:
    cleanup_member()
    try:
        with SessionLocal() as db:
            member = Member(
                email=TEST_EMAIL,
                display_name="Route Member",
                good_standing=True,
                submission_review_required=True,
            )
            db.add(member)
            db.commit()
            member_id = member.id

        response = admin_client.post(
            f"/members/{member_id}",
            data={
                "display_name": "Route Member",
                "email": TEST_EMAIL,
                "good_standing": "true",
                "submission_review_required": "false",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/members"
        with SessionLocal() as db:
            member = db.get(Member, member_id)
            assert member is not None
            assert member.submission_review_required is False
    finally:
        cleanup_member()


def test_members_can_be_bulk_edited(admin_client) -> None:
    cleanup_member()
    try:
        with SessionLocal() as db:
            member = Member(
                email=TEST_EMAIL,
                display_name="Route Member",
                good_standing=True,
                submission_review_required=True,
            )
            inactive_member = Member(
                email=TEST_EMAIL_2,
                display_name="Second Route Member",
                good_standing=False,
                submission_review_required=True,
                deactivated_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
            db.add_all([member, inactive_member])
            db.commit()
            member_id = member.id
            inactive_member_id = inactive_member.id

        page = admin_client.get("/members/bulk-edit")
        assert page.status_code == 200
        assert "Bulk edit members" in page.text
        assert "Trust Visible" in page.text

        response = admin_client.post(
            "/members/bulk-edit",
            data={
                "member_id": [str(member_id), str(inactive_member_id)],
                f"display_name_{member_id}": "Bulk Route Member",
                f"email_{member_id}": TEST_EMAIL,
                f"paypal_email_{member_id}": PAYPAL_EMAIL,
                f"mailing_list_email_{member_id}": LIST_EMAIL,
                f"good_standing_{member_id}": "true",
                f"active_{member_id}": "true",
                f"display_name_{inactive_member_id}": "Second Bulk Route Member",
                f"email_{inactive_member_id}": TEST_EMAIL_2,
                f"paypal_email_{inactive_member_id}": PAYPAL_EMAIL_2,
                f"mailing_list_email_{inactive_member_id}": LIST_EMAIL_2,
                f"is_admin_{inactive_member_id}": "true",
                f"good_standing_{inactive_member_id}": "true",
                f"active_{inactive_member_id}": "true",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/members?bulk_updated=2"
        with SessionLocal() as db:
            member = db.get(Member, member_id)
            inactive_member = db.get(Member, inactive_member_id)
            assert member is not None
            assert inactive_member is not None
            assert member.display_name == "Bulk Route Member"
            assert member.submission_review_required is False
            assert member.good_standing is True
            assert member.deactivated_at is None
            assert inactive_member.display_name == "Second Bulk Route Member"
            assert inactive_member.is_admin is True
            assert inactive_member.good_standing is True
            assert inactive_member.submission_review_required is False
            assert inactive_member.deactivated_at is None
            aliases = {
                alias.email
                for alias in db.scalars(
                    select(MemberEmail).where(
                        MemberEmail.member_id.in_([member_id, inactive_member_id])
                    )
                )
            }
            assert {PAYPAL_EMAIL, LIST_EMAIL, PAYPAL_EMAIL_2, LIST_EMAIL_2} <= aliases

        index = admin_client.get("/members?bulk_updated=2")
        assert "Updated 2 members." in index.text
    finally:
        cleanup_member()


def test_bulk_edit_keeps_current_admin_active_and_admin(admin_client) -> None:
    response = admin_client.get("/members/bulk-edit")
    assert response.status_code == 200

    with SessionLocal() as db:
        admin = db.scalar(select(Member).where(Member.email == ADMIN_EMAIL))
        assert admin is not None
        admin_id = admin.id

    response = admin_client.post(
        "/members/bulk-edit",
        data={
            "member_id": [str(admin_id)],
            f"display_name_{admin_id}": "Test Admin",
            f"email_{admin_id}": ADMIN_EMAIL,
            f"paypal_email_{admin_id}": "",
            f"mailing_list_email_{admin_id}": "",
            f"good_standing_{admin_id}": "true",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    with SessionLocal() as db:
        admin = db.get(Member, admin_id)
        assert admin is not None
        assert admin.is_admin is True
        assert admin.deactivated_at is None


def test_member_can_be_deactivated(admin_client) -> None:
    cleanup_member()
    try:
        with SessionLocal() as db:
            member = Member(email=TEST_EMAIL, display_name="Route Member")
            db.add(member)
            db.commit()
            member_id = member.id

        client = admin_client
        response = client.post(f"/members/{member_id}/deactivate", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/members"

        with SessionLocal() as db:
            member = db.scalar(select(Member).where(Member.email == TEST_EMAIL))
            assert member is not None
            assert member.deactivated_at is not None
    finally:
        cleanup_member()
