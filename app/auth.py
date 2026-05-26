from __future__ import annotations

from urllib.parse import quote

from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from itsdangerous import BadSignature, BadTimeSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Member
from app.db.session import get_db


SESSION_COOKIE_NAME = "trophy_case_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
SESSION_SALT = "trophy-case-auth"


def serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.app_secret_key, salt=SESSION_SALT)


def session_token_for_member(member: Member) -> str:
    return serializer().dumps({"member_id": member.id})


def member_id_from_request(request: Request) -> int | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    try:
        payload = serializer().loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, BadTimeSignature):
        return None

    member_id = payload.get("member_id")
    return member_id if isinstance(member_id, int) else None


def set_session_cookie(response: Response, member: Member) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token_for_member(member),
        httponly=True,
        max_age=SESSION_MAX_AGE_SECONDS,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME)


def require_admin(
    request: Request,
    db: Session = Depends(get_db),
) -> Member:
    member_id = member_id_from_request(request)
    member = db.get(Member, member_id) if member_id is not None else None
    if member is None or not member.is_admin or member.deactivated_at is not None:
        raise HTTPException(
            status_code=303,
            headers={"Location": login_path_for_request(request)},
        )
    return member


def require_member(
    request: Request,
    db: Session = Depends(get_db),
) -> Member:
    member_id = member_id_from_request(request)
    member = db.get(Member, member_id) if member_id is not None else None
    if member is None or member.deactivated_at is not None:
        raise HTTPException(
            status_code=303,
            headers={"Location": member_login_path_for_request(request)},
        )
    return member


def login_path_for_request(request: Request) -> str:
    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return f"/login?next={quote(target, safe='')}"


def member_login_path_for_request(request: Request) -> str:
    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return f"/member-login?next={quote(target, safe='')}"


def safe_redirect_target(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/leaderboard"
    return value
