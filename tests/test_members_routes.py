from __future__ import annotations

from sqlalchemy import delete, select

from app.db.models import Member, MemberEmail, MemberEmailKind, Result
from app.db.session import SessionLocal


TEST_EMAIL = "route-member@example.test"
PAYPAL_EMAIL = "route-paypal@example.test"
LIST_EMAIL = "route-list@example.test"


def cleanup_member() -> None:
    with SessionLocal() as db:
        member_ids = list(
            db.scalars(
                select(Member.id).where(Member.email.in_([TEST_EMAIL, PAYPAL_EMAIL, LIST_EMAIL]))
            )
        )
        alias_member_ids = list(
            db.scalars(
                select(MemberEmail.member_id).where(
                    MemberEmail.email.in_([TEST_EMAIL, PAYPAL_EMAIL, LIST_EMAIL])
                )
            )
        )
        member_ids.extend(alias_member_ids)
        if member_ids:
            db.execute(delete(Result).where(Result.member_id.in_(member_ids)))
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
