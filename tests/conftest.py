from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.models import AppSetting, AuditLog, Member
from app.db.session import SessionLocal
from app.main import app
from app.routers.auth import reset_member_login_rate_limits
from app.core.config import settings
from app.services.csrf import CSRF_COOKIE_NAME, csrf_token_from_signed_cookie
from app.auth import SESSION_COOKIE_NAME


ADMIN_EMAIL = "test-admin@example.test"


class CsrfTestClient(TestClient):
    def post(self, url, *args, data=None, files=None, **kwargs):
        if self.cookies.get(SESSION_COOKIE_NAME):
            token = csrf_token_from_signed_cookie(self.cookies.get(CSRF_COOKIE_NAME))
            if token is None:
                self.get("/results")
                token = csrf_token_from_signed_cookie(self.cookies.get(CSRF_COOKIE_NAME))
            if token is not None:
                if data is None:
                    data = {"csrf_token": token}
                elif isinstance(data, dict) and "csrf_token" not in data:
                    data = {**data, "csrf_token": token}
        return super().post(url, *args, data=data, files=files, **kwargs)


@pytest.fixture(autouse=True)
def reset_app_settings() -> Generator[None]:
    original_session_cookie_secure = settings.session_cookie_secure
    original_public_base_url = settings.public_base_url
    settings.session_cookie_secure = False
    settings.public_base_url = None
    cleanup_app_settings()
    reset_member_login_rate_limits()
    try:
        yield
    finally:
        settings.session_cookie_secure = original_session_cookie_secure
        settings.public_base_url = original_public_base_url
        cleanup_app_settings()
        reset_member_login_rate_limits()


@pytest.fixture
def admin_client() -> Generator[TestClient]:
    cleanup_admin()
    with SessionLocal() as db:
        db.add(Member(email=ADMIN_EMAIL, display_name="Test Admin", is_admin=True))
        db.commit()

    client = CsrfTestClient(app)
    response = client.post(
        "/login",
        data={"email": ADMIN_EMAIL, "next": "/results"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    try:
        yield client
    finally:
        cleanup_admin()


def cleanup_admin() -> None:
    with SessionLocal() as db:
        db.execute(delete(AuditLog))
        member_ids = list(db.scalars(select(Member.id).where(Member.email == ADMIN_EMAIL)))
        if member_ids:
            db.execute(delete(Member).where(Member.id.in_(member_ids)))
            db.commit()


def cleanup_app_settings() -> None:
    with SessionLocal() as db:
        db.execute(delete(AuditLog))
        db.execute(delete(AppSetting))
        db.commit()
