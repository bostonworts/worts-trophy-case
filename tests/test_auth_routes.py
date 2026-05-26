from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.models import AuditLog, Member, MemberEmail, MemberEmailKind, MemberLoginChallenge
from app.db.session import SessionLocal
from app.main import app
from app.core.config import settings
from app.auth import SESSION_COOKIE_NAME, session_token_for_member
from app.services.email import EmailDeliveryError
from app.services.csrf import CSRF_COOKIE_NAME, csrf_token_from_signed_cookie


AUTH_EMAIL = "auth-admin@example.test"
FIRST_ADMIN_EMAIL = "first-admin@example.test"
MEMBER_LOGIN_EMAIL = "member-login@example.test"
MEMBER_PAYPAL_EMAIL = "member-paypal@example.test"
MEMBER_LIST_EMAIL = "member-list@example.test"


def magic_token_from_link(link: str) -> str:
    values = parse_qs(urlparse(link).query).get("token")
    assert values
    return values[0]


def cleanup_auth_member() -> None:
    with SessionLocal() as db:
        member_ids = list(
            db.scalars(
                select(Member.id).where(
                    Member.email.in_([AUTH_EMAIL, FIRST_ADMIN_EMAIL, MEMBER_LOGIN_EMAIL])
                )
            )
        )
        alias_member_ids = list(
            db.scalars(
                select(MemberEmail.member_id).where(
                    MemberEmail.email.in_(
                        [MEMBER_LOGIN_EMAIL, MEMBER_PAYPAL_EMAIL, MEMBER_LIST_EMAIL]
                    )
                )
            )
        )
        member_ids.extend(alias_member_ids)
        if member_ids:
            db.execute(delete(AuditLog).where(AuditLog.actor_member_id.in_(member_ids)))
            db.execute(
                delete(MemberLoginChallenge).where(MemberLoginChallenge.member_id.in_(member_ids))
            )
            db.execute(delete(Member).where(Member.id.in_(member_ids)))
            db.commit()


def remove_active_admins_temporarily() -> dict[int, bool]:
    with SessionLocal() as db:
        members = db.scalars(select(Member)).all()
        admin_states = {member.id: member.is_admin for member in members}
        for member in members:
            member.is_admin = False
        db.commit()
        return admin_states


def restore_admin_states(admin_states: dict[int, bool]) -> None:
    with SessionLocal() as db:
        for member_id, is_admin in admin_states.items():
            member = db.get(Member, member_id)
            if member is not None:
                member.is_admin = is_admin
        db.commit()


def authenticated_client_for_member(member_id: int) -> TestClient:
    with SessionLocal() as db:
        member = db.get(Member, member_id)
        assert member is not None
        token = session_token_for_member(member)
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    return client


def test_public_pages_do_not_require_login() -> None:
    client = TestClient(app)

    root_response = client.get("/", follow_redirects=False)
    assert root_response.status_code == 303
    assert root_response.headers["location"] == "/leaderboard"
    assert client.get("/results").status_code == 200
    assert client.get("/competitions").status_code == 200
    assert client.get("/leaderboard").status_code == 200


def test_leaderboard_rejects_invalid_season() -> None:
    client = TestClient(app)

    response = client.get("/leaderboard?season=bad")

    assert response.status_code == 422
    assert response.json()["detail"] == "season must use YYYY-YYYY."


def test_admin_page_redirects_to_login() -> None:
    client = TestClient(app)

    response = client.get("/members", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/member-login?next=%2Fmembers"


def test_admin_can_login_with_member_email_and_logout(monkeypatch) -> None:
    cleanup_auth_member()
    sent_logins = []
    monkeypatch.setattr(
        "app.routers.auth.send_member_login_code",
        lambda *, to_email, code, magic_link: sent_logins.append(
            {"to_email": to_email, "code": code, "magic_link": magic_link}
        ),
    )
    try:
        with SessionLocal() as db:
            db.add(Member(email=AUTH_EMAIL, display_name="Auth Admin", is_admin=True))
            db.commit()

        client = TestClient(app)
        request_response = client.post(
            "/member-login",
            data={"email": AUTH_EMAIL, "next": "/members"},
        )
        assert request_response.status_code == 200
        assert sent_logins and sent_logins[0]["to_email"] == AUTH_EMAIL

        login_response = client.post(
            "/member-login/verify",
            data={
                "email": AUTH_EMAIL,
                "login_code": sent_logins[0]["code"],
                "next": "/members",
            },
            follow_redirects=False,
        )
        assert login_response.status_code == 303
        assert login_response.headers["location"] == "/members"
        assert client.get("/members").status_code == 200

        csrf_token = csrf_token_from_signed_cookie(client.cookies.get(CSRF_COOKIE_NAME))
        assert csrf_token is not None
        logout_response = client.post(
            "/logout",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )

        assert logout_response.status_code == 303
        assert logout_response.headers["location"] == "/leaderboard"
        assert client.get("/members", follow_redirects=False).status_code == 303
    finally:
        cleanup_auth_member()


def test_legacy_admin_login_redirects_to_member_login() -> None:
    cleanup_auth_member()
    try:
        with SessionLocal() as db:
            member = Member(email=AUTH_EMAIL, display_name="Auth Admin", is_admin=True)
            db.add(member)
            db.commit()

        client = TestClient(app)
        get_response = client.get("/login?next=/members", follow_redirects=False)
        post_response = client.post(
            "/login",
            data={"email": AUTH_EMAIL, "next": "/members"},
            follow_redirects=False,
        )

        assert get_response.status_code == 303
        assert get_response.headers["location"] == "/member-login?next=%2Fmembers"
        assert post_response.status_code == 303
        assert post_response.headers["location"] == "/member-login?next=%2Fmembers"
    finally:
        cleanup_auth_member()


def test_admin_can_login_with_member_roster_alias(monkeypatch) -> None:
    cleanup_auth_member()
    sent_logins = []
    monkeypatch.setattr(
        "app.routers.auth.send_member_login_code",
        lambda *, to_email, code, magic_link: sent_logins.append(
            {"to_email": to_email, "code": code, "magic_link": magic_link}
        ),
    )
    try:
        with SessionLocal() as db:
            member = Member(email=AUTH_EMAIL, display_name="Auth Admin", is_admin=True)
            db.add(member)
            db.flush()
            db.add(
                MemberEmail(
                    member=member,
                    email=MEMBER_LIST_EMAIL,
                    kind=MemberEmailKind.MAILING_LIST,
                )
            )
            db.commit()

        client = TestClient(app)
        request_response = client.post(
            "/member-login",
            data={"email": MEMBER_LIST_EMAIL, "next": "/members"},
        )
        assert request_response.status_code == 200
        assert sent_logins and sent_logins[0]["to_email"] == MEMBER_LIST_EMAIL

        response = client.post(
            "/member-login/verify",
            data={
                "email": MEMBER_LIST_EMAIL,
                "login_code": sent_logins[0]["code"],
                "next": "/members",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/members"
    finally:
        cleanup_auth_member()


def test_member_login_does_not_send_for_alias_owned_by_ineligible_member(monkeypatch) -> None:
    cleanup_auth_member()
    sent_logins = []
    monkeypatch.setattr(
        "app.routers.auth.send_member_login_code",
        lambda *, to_email, code, magic_link: sent_logins.append(
            {"to_email": to_email, "code": code, "magic_link": magic_link}
        ),
    )
    try:
        with SessionLocal() as db:
            member = Member(
                email=MEMBER_LOGIN_EMAIL,
                display_name="Other Member",
                good_standing=False,
            )
            db.add(member)
            db.flush()
            db.add(
                MemberEmail(
                    member=member,
                    email=AUTH_EMAIL,
                    kind=MemberEmailKind.MAILING_LIST,
                )
            )
            db.commit()

        response = TestClient(app).post(
            "/member-login",
            data={"email": AUTH_EMAIL, "next": "/members"},
        )

        assert response.status_code == 200
        assert "If that email belongs to a member in good standing" in response.text
        assert sent_logins == []
    finally:
        cleanup_auth_member()


def test_authenticated_post_requires_csrf_token() -> None:
    cleanup_auth_member()
    try:
        with SessionLocal() as db:
            member = Member(email=AUTH_EMAIL, display_name="Auth Admin", is_admin=True)
            db.add(member)
            db.commit()
            member_id = member.id

        client = authenticated_client_for_member(member_id)
        response = client.post(
            "/admin/data/clear-results",
            data={"confirm_text": "CLEAR RESULTS"},
            follow_redirects=False,
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Invalid CSRF token."
    finally:
        cleanup_auth_member()


def test_existing_admin_setup_login_redirects_to_member_login(monkeypatch) -> None:
    cleanup_auth_member()
    monkeypatch.setattr(settings, "admin_login_code", "secret-code")
    try:
        with SessionLocal() as db:
            db.add(Member(email=AUTH_EMAIL, display_name="Auth Admin", is_admin=True))
            db.commit()

        client = TestClient(app)
        response = client.post(
            "/login",
            data={"email": AUTH_EMAIL, "next": "/members", "login_code": "secret-code"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/member-login?next=%2Fmembers"
    finally:
        cleanup_auth_member()


def test_first_admin_setup_attempts_are_rate_limited(monkeypatch) -> None:
    cleanup_auth_member()
    admin_states = remove_active_admins_temporarily()
    monkeypatch.setattr(settings, "admin_setup_code", "setup-secret")
    try:
        client = TestClient(app)
        responses = [
            client.post(
                "/login",
                data={"email": FIRST_ADMIN_EMAIL, "next": "/members", "login_code": "bad"},
            )
            for _ in range(settings.admin_login_attempt_limit + 1)
        ]

        assert [response.status_code for response in responses[:-1]] == [403] * (
            settings.admin_login_attempt_limit
        )
        assert responses[-1].status_code == 429
        assert "Too many login attempts" in responses[-1].text
    finally:
        cleanup_auth_member()
        restore_admin_states(admin_states)


def test_first_admin_bootstrap_requires_setup_code(monkeypatch) -> None:
    cleanup_auth_member()
    admin_states = remove_active_admins_temporarily()
    monkeypatch.setattr(settings, "admin_login_code", None)
    monkeypatch.setattr(settings, "admin_setup_code", None)
    try:
        client = TestClient(app)
        disabled_response = client.post(
            "/login",
            data={"email": FIRST_ADMIN_EMAIL, "next": "/members"},
        )
        assert disabled_response.status_code == 403
        assert "First admin setup is disabled." in disabled_response.text

        monkeypatch.setattr(settings, "admin_setup_code", "setup-secret")
        bad_response = client.post(
            "/login",
            data={"email": FIRST_ADMIN_EMAIL, "next": "/members", "login_code": "bad"},
        )
        good_response = client.post(
            "/login",
            data={
                "email": FIRST_ADMIN_EMAIL,
                "next": "/members",
                "login_code": "setup-secret",
            },
            follow_redirects=False,
        )

        assert bad_response.status_code == 403
        assert "Enter the first-admin setup code." in bad_response.text
        assert good_response.status_code == 303
        with SessionLocal() as db:
            member = db.scalar(select(Member).where(Member.email == FIRST_ADMIN_EMAIL))
            assert member is not None
            assert member.is_admin is True
    finally:
        cleanup_auth_member()
        restore_admin_states(admin_states)


def test_member_in_good_standing_can_login_with_list_email(monkeypatch) -> None:
    cleanup_auth_member()
    sent_logins = []
    monkeypatch.setattr(
        "app.routers.auth.send_member_login_code",
        lambda *, to_email, code, magic_link: sent_logins.append(
            {"to_email": to_email, "code": code, "magic_link": magic_link}
        ),
    )
    try:
        with SessionLocal() as db:
            member = Member(
                email=MEMBER_LOGIN_EMAIL,
                display_name="Member Login",
                good_standing=True,
            )
            db.add(member)
            db.flush()
            db.add_all(
                [
                    MemberEmail(
                        member=member,
                        email=MEMBER_PAYPAL_EMAIL,
                        kind=MemberEmailKind.PAYPAL,
                    ),
                    MemberEmail(
                        member=member,
                        email=MEMBER_LIST_EMAIL,
                        kind=MemberEmailKind.MAILING_LIST,
                    ),
                ]
            )
            db.commit()

        client = TestClient(app)
        request_response = client.post(
            "/member-login",
            data={"email": MEMBER_LIST_EMAIL, "next": "/results"},
        )

        assert request_response.status_code == 200
        assert "If that email belongs to a member in good standing" in request_response.text
        assert sent_logins and sent_logins[0]["to_email"] == MEMBER_LIST_EMAIL

        token = magic_token_from_link(sent_logins[0]["magic_link"])
        with SessionLocal() as db:
            challenge = db.scalar(
                select(MemberLoginChallenge)
                .where(MemberLoginChallenge.email == MEMBER_LIST_EMAIL)
                .order_by(MemberLoginChallenge.created_at.desc())
                .limit(1)
            )
            assert challenge is not None
            assert challenge.code_hash != sent_logins[0]["code"]
            assert challenge.token_hash is not None
            assert challenge.token_hash != token

        verify_response = client.post(
            "/member-login/verify",
            data={
                "email": MEMBER_LIST_EMAIL,
                "login_code": sent_logins[0]["code"],
                "next": "/results",
            },
            follow_redirects=False,
        )

        assert verify_response.status_code == 303
        assert verify_response.headers["location"] == "/results"
        me_response = client.get("/me", follow_redirects=False)
        assert me_response.status_code == 303
        assert me_response.headers["location"].startswith("/members/")
        assert client.get("/members", follow_redirects=False).status_code == 303
        link_replay_response = TestClient(app).get(
            sent_logins[0]["magic_link"],
            follow_redirects=False,
        )
        assert link_replay_response.status_code == 403
    finally:
        cleanup_auth_member()


def test_member_login_does_not_send_code_when_not_in_good_standing(monkeypatch) -> None:
    cleanup_auth_member()
    sent_logins = []
    monkeypatch.setattr(
        "app.routers.auth.send_member_login_code",
        lambda *, to_email, code, magic_link: sent_logins.append(
            {"to_email": to_email, "code": code, "magic_link": magic_link}
        ),
    )
    try:
        with SessionLocal() as db:
            db.add(
                Member(
                    email=MEMBER_LOGIN_EMAIL,
                    display_name="Member Login",
                    good_standing=False,
                )
            )
            db.commit()

        response = TestClient(app).post(
            "/member-login",
            data={"email": MEMBER_LOGIN_EMAIL, "next": "/results"},
        )

        assert response.status_code == 200
        assert "If that email belongs to a member in good standing" in response.text
        assert sent_logins == []
    finally:
        cleanup_auth_member()


def test_member_login_email_delivery_failure_is_handled(monkeypatch) -> None:
    cleanup_auth_member()

    def fail_delivery(*, to_email: str, code: str, magic_link: str) -> None:
        raise EmailDeliveryError("boom")

    monkeypatch.setattr("app.routers.auth.send_member_login_code", fail_delivery)
    try:
        with SessionLocal() as db:
            db.add(
                Member(
                    email=MEMBER_LOGIN_EMAIL,
                    display_name="Member Login",
                    good_standing=True,
                )
            )
            db.commit()

        response = TestClient(app).post(
            "/member-login",
            data={"email": MEMBER_LOGIN_EMAIL, "next": "/results"},
        )

        assert response.status_code == 502
        assert "could not send a login email" in response.text
        with SessionLocal() as db:
            challenge_count = len(
                db.scalars(
                    select(MemberLoginChallenge).where(
                        MemberLoginChallenge.email == MEMBER_LOGIN_EMAIL
                    )
                ).all()
            )
        assert challenge_count == 0
    finally:
        cleanup_auth_member()


def test_member_login_code_requests_are_rate_limited(monkeypatch) -> None:
    cleanup_auth_member()
    sent_logins = []
    monkeypatch.setattr(
        "app.routers.auth.send_member_login_code",
        lambda *, to_email, code, magic_link: sent_logins.append(
            {"to_email": to_email, "code": code, "magic_link": magic_link}
        ),
    )
    try:
        with SessionLocal() as db:
            db.add(
                Member(
                    email=MEMBER_LOGIN_EMAIL,
                    display_name="Member Login",
                    good_standing=True,
                )
            )
            db.commit()

        client = TestClient(app)
        responses = [
            client.post(
                "/member-login",
                data={"email": MEMBER_LOGIN_EMAIL, "next": "/results"},
            )
            for _ in range(settings.member_login_request_limit + 1)
        ]

        assert [response.status_code for response in responses[:-1]] == [200] * (
            settings.member_login_request_limit
        )
        assert responses[-1].status_code == 429
        assert "Too many login attempts" in responses[-1].text
        assert len(sent_logins) == settings.member_login_request_limit
    finally:
        cleanup_auth_member()


def test_member_in_good_standing_can_login_with_magic_link(monkeypatch) -> None:
    cleanup_auth_member()
    sent_logins = []
    monkeypatch.setattr(
        "app.routers.auth.send_member_login_code",
        lambda *, to_email, code, magic_link: sent_logins.append(
            {"to_email": to_email, "code": code, "magic_link": magic_link}
        ),
    )
    try:
        with SessionLocal() as db:
            db.add(
                Member(
                    email=MEMBER_LOGIN_EMAIL,
                    display_name="Member Login",
                    good_standing=True,
                )
            )
            db.commit()

        client = TestClient(app)
        request_response = client.post(
            "/member-login",
            data={"email": MEMBER_LOGIN_EMAIL, "next": "/results"},
        )

        assert request_response.status_code == 200
        assert sent_logins and sent_logins[0]["to_email"] == MEMBER_LOGIN_EMAIL
        link = sent_logins[0]["magic_link"]
        assert urlparse(link).path == "/member-login/verify"
        assert parse_qs(urlparse(link).query)["next"] == ["/results"]

        verify_response = client.get(link, follow_redirects=False)

        assert verify_response.status_code == 303
        assert verify_response.headers["location"] == "/results"
        me_response = client.get("/me", follow_redirects=False)
        assert me_response.status_code == 303
        assert me_response.headers["location"].startswith("/members/")

        with SessionLocal() as db:
            challenge = db.scalar(
                select(MemberLoginChallenge)
                .where(MemberLoginChallenge.email == MEMBER_LOGIN_EMAIL)
                .limit(1)
            )
            assert challenge is not None
            assert challenge.used_at is not None

        replay_response = TestClient(app).get(link, follow_redirects=False)

        assert replay_response.status_code == 403
        assert "invalid or expired" in replay_response.text
    finally:
        cleanup_auth_member()


def test_member_magic_link_expires_with_challenge(monkeypatch) -> None:
    cleanup_auth_member()
    sent_logins = []
    monkeypatch.setattr(
        "app.routers.auth.send_member_login_code",
        lambda *, to_email, code, magic_link: sent_logins.append(
            {"to_email": to_email, "code": code, "magic_link": magic_link}
        ),
    )
    try:
        with SessionLocal() as db:
            db.add(
                Member(
                    email=MEMBER_LOGIN_EMAIL,
                    display_name="Member Login",
                    good_standing=True,
                )
            )
            db.commit()

        client = TestClient(app)
        client.post(
            "/member-login",
            data={"email": MEMBER_LOGIN_EMAIL, "next": "/results"},
        )
        with SessionLocal() as db:
            challenge = db.scalar(
                select(MemberLoginChallenge).where(
                    MemberLoginChallenge.email == MEMBER_LOGIN_EMAIL
                )
            )
            assert challenge is not None
            challenge.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            db.commit()

        response = client.get(sent_logins[0]["magic_link"], follow_redirects=False)

        assert response.status_code == 403
        assert "invalid or expired" in response.text
        assert client.get("/me", follow_redirects=False).status_code == 303
    finally:
        cleanup_auth_member()


def test_member_magic_link_rechecks_eligibility(monkeypatch) -> None:
    cleanup_auth_member()
    sent_logins = []
    monkeypatch.setattr(
        "app.routers.auth.send_member_login_code",
        lambda *, to_email, code, magic_link: sent_logins.append(
            {"to_email": to_email, "code": code, "magic_link": magic_link}
        ),
    )
    try:
        with SessionLocal() as db:
            db.add(
                Member(
                    email=MEMBER_LOGIN_EMAIL,
                    display_name="Member Login",
                    good_standing=True,
                )
            )
            db.commit()

        client = TestClient(app)
        client.post(
            "/member-login",
            data={"email": MEMBER_LOGIN_EMAIL, "next": "/results"},
        )
        with SessionLocal() as db:
            member = db.scalar(select(Member).where(Member.email == MEMBER_LOGIN_EMAIL))
            assert member is not None
            member.good_standing = False
            db.commit()

        response = client.get(sent_logins[0]["magic_link"], follow_redirects=False)

        assert response.status_code == 403
        assert "invalid or expired" in response.text
        with SessionLocal() as db:
            challenge = db.scalar(
                select(MemberLoginChallenge).where(
                    MemberLoginChallenge.email == MEMBER_LOGIN_EMAIL
                )
            )
            assert challenge is not None
            assert challenge.used_at is None
    finally:
        cleanup_auth_member()


def test_member_magic_link_uses_public_base_url(monkeypatch) -> None:
    cleanup_auth_member()
    sent_logins = []
    monkeypatch.setattr(settings, "public_base_url", "https://club.example.test/trophy/")
    monkeypatch.setattr(
        "app.routers.auth.send_member_login_code",
        lambda *, to_email, code, magic_link: sent_logins.append(
            {"to_email": to_email, "code": code, "magic_link": magic_link}
        ),
    )
    try:
        with SessionLocal() as db:
            db.add(
                Member(
                    email=MEMBER_LOGIN_EMAIL,
                    display_name="Member Login",
                    good_standing=True,
                )
            )
            db.commit()

        response = TestClient(app).post(
            "/member-login",
            data={"email": MEMBER_LOGIN_EMAIL, "next": "/results"},
        )

        assert response.status_code == 200
        link = sent_logins[0]["magic_link"]
        parsed_link = urlparse(link)
        assert parsed_link.scheme == "https"
        assert parsed_link.netloc == "club.example.test"
        assert parsed_link.path == "/trophy/member-login/verify"
        assert parse_qs(parsed_link.query)["next"] == ["/results"]
        assert parse_qs(parsed_link.query)["token"]
    finally:
        cleanup_auth_member()


def test_member_magic_link_verification_is_rate_limited() -> None:
    client = TestClient(app)
    responses = [
        client.get(
            "/member-login/verify",
            params={"token": "not-a-real-login-token", "next": "/results"},
        )
        for _ in range(settings.member_login_verify_limit + 1)
    ]

    assert [response.status_code for response in responses[:-1]] == [403] * (
        settings.member_login_verify_limit
    )
    assert responses[-1].status_code == 429
    assert "Too many login attempts" in responses[-1].text
