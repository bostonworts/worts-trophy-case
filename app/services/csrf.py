from __future__ import annotations

import hmac
from secrets import token_urlsafe

from fastapi import Form, HTTPException, Request
from fastapi.responses import Response
from itsdangerous import BadSignature, URLSafeSerializer

from app.auth import SESSION_COOKIE_NAME
from app.core.config import settings


CSRF_COOKIE_NAME = "trophy_case_csrf"
CSRF_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
CSRF_SALT = "trophy-case-csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def csrf_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.app_secret_key, salt=CSRF_SALT)


def new_csrf_token() -> str:
    return token_urlsafe(32)


def signed_csrf_token(token: str) -> str:
    return csrf_serializer().dumps({"token": token})


def csrf_token_from_signed_cookie(value: str | None) -> str | None:
    if not value:
        return None
    try:
        payload = csrf_serializer().loads(value)
    except BadSignature:
        return None
    token = payload.get("token")
    return token if isinstance(token, str) and token else None


def csrf_token_for_request(request: Request) -> str:
    token = csrf_token_from_signed_cookie(request.cookies.get(CSRF_COOKIE_NAME))
    return token or new_csrf_token()


def set_csrf_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        CSRF_COOKIE_NAME,
        signed_csrf_token(token),
        httponly=True,
        max_age=CSRF_COOKIE_MAX_AGE_SECONDS,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )


async def require_csrf(
    request: Request,
    csrf_token: str | None = Form(None),
) -> None:
    if request.method in SAFE_METHODS:
        return
    if SESSION_COOKIE_NAME not in request.cookies:
        return

    expected_token = getattr(request.state, "csrf_token", None)
    if not expected_token or not csrf_token or not hmac.compare_digest(csrf_token, expected_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token.")
