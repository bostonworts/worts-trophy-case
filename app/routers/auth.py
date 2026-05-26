from __future__ import annotations

import hashlib
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import clear_session_cookie, require_member, safe_redirect_target, set_session_cookie
from app.core.config import settings
from app.db.models import Member
from app.db.session import get_db
from app.services.audit import record_audit
from app.services.email import EmailDeliveryError, send_member_login_code
from app.services.member_auth import (
    consume_login_code,
    consume_login_token,
    email_for_login_token,
    eligible_member_for_login_email,
    ensure_primary_email_alias,
    issue_login_challenge,
    member_for_login_email,
    normalize_email,
)
from app.services.rate_limit import InMemoryRateLimiter
from app.templating import templates

router = APIRouter()
admin_login_limiter = InMemoryRateLimiter(
    limit=settings.admin_login_attempt_limit,
    window_seconds=settings.admin_login_rate_limit_window_seconds,
)
member_login_request_limiter = InMemoryRateLimiter(
    limit=settings.member_login_request_limit,
    window_seconds=settings.member_login_rate_limit_window_seconds,
)
member_login_verify_limiter = InMemoryRateLimiter(
    limit=settings.member_login_verify_limit,
    window_seconds=settings.member_login_rate_limit_window_seconds,
)


@router.get("/login", response_class=HTMLResponse)
def login_form(
    request: Request,
    next_url: str = Query("/results", alias="next"),
) -> HTMLResponse:
    return render_login(request, next_url=safe_redirect_target(next_url))


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    login_code: str = Form(""),
    next_url: str = Form("/results", alias="next"),
    db: Session = Depends(get_db),
) -> Response:
    target = safe_redirect_target(next_url)
    normalized_email = normalize_email(email)

    if not settings.local_login_enabled:
        return render_login(
            request,
            next_url=target,
            email=normalized_email,
            errors=["Local login is disabled."],
            status_code=403,
        )

    retry_after = admin_login_limiter.hit(admin_login_rate_limit_key(request, normalized_email))
    if retry_after is not None:
        return render_login(
            request,
            next_url=target,
            email=normalized_email,
            errors=[rate_limit_message(retry_after)],
            status_code=429,
        )

    member = member_for_login_email(db, normalized_email)
    admin_count = db.scalar(select(func.count()).select_from(Member).where(Member.is_admin))

    if admin_count == 0:
        if not settings.admin_setup_code:
            return render_login(
                request,
                next_url=target,
                email=normalized_email,
                errors=["First admin setup is disabled."],
                status_code=403,
            )
        if login_code != settings.admin_setup_code:
            return render_login(
                request,
                next_url=target,
                email=normalized_email,
                errors=["Enter the first-admin setup code."],
                status_code=403,
            )

    elif settings.admin_login_code and login_code != settings.admin_login_code:
        return render_login(
            request,
            next_url=target,
            email=normalized_email,
            errors=["Enter the admin login code."],
            status_code=403,
        )

    if member is None and admin_count == 0:
        member = Member(
            email=normalized_email,
            display_name=display_name_from_email(normalized_email),
            is_admin=True,
        )
        db.add(member)
        db.flush()
    elif member is not None and admin_count == 0:
        member.is_admin = True
        member.deactivated_at = None
    elif member is None or not member.is_admin or member.deactivated_at is not None:
        return render_login(
            request,
            next_url=target,
            email=normalized_email,
            errors=["Use an active admin member email."],
            status_code=403,
        )

    try:
        ensure_primary_email_alias(db, member)
    except ValueError:
        db.rollback()
        return render_login(
            request,
            next_url=target,
            email=normalized_email,
            errors=["That email is already attached to another member."],
            status_code=403,
        )
    db.commit()
    record_audit(
        db,
        actor=member,
        action="login",
        entity_type="member",
        entity_id=member.id,
        summary=f"{member.display_name} logged in.",
    )
    db.commit()
    admin_login_limiter.reset(admin_login_rate_limit_key(request, normalized_email))
    response = RedirectResponse(target, status_code=303)
    set_session_cookie(response, member)
    return response


@router.get("/member-login", response_class=HTMLResponse)
def member_login_form(
    request: Request,
    next_url: str = Query("/me", alias="next"),
) -> HTMLResponse:
    return render_member_login(request, next_url=safe_redirect_target(next_url))


@router.post("/member-login", response_class=HTMLResponse)
def request_member_login_code(
    request: Request,
    email: str = Form(...),
    next_url: str = Form("/me", alias="next"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    target = safe_redirect_target(next_url)
    normalized_email = normalize_email(email)
    if not settings.local_login_enabled:
        return render_member_login(
            request,
            next_url=target,
            email=normalized_email,
            errors=["Member login is disabled."],
            status_code=403,
        )

    retry_after = member_login_request_limiter.hit(
        member_login_rate_limit_key(request, "request", normalized_email)
    )
    if retry_after is not None:
        return render_member_login(
            request,
            next_url=target,
            email=normalized_email,
            errors=[rate_limit_message(retry_after)],
            status_code=429,
        )

    member = eligible_member_for_login_email(db, normalized_email)
    if member is not None:
        challenge = issue_login_challenge(db, member=member, email=normalized_email)
        try:
            send_member_login_code(
                to_email=normalized_email,
                code=challenge.code,
                magic_link=member_login_magic_link(
                    request,
                    token=challenge.magic_token,
                    next_url=target,
                ),
            )
        except EmailDeliveryError:
            db.rollback()
            return render_member_login(
                request,
                next_url=target,
                email=normalized_email,
                errors=["We could not send a login email right now. Try again later."],
                status_code=502,
            )
        db.commit()

    return render_member_login(
        request,
        next_url=target,
        email=normalized_email,
        code_requested=True,
        summary=(
            "If that email belongs to a member in good standing, "
            "a login link and code were sent."
        ),
    )


@router.post("/member-login/verify")
def verify_member_login_code(
    request: Request,
    email: str = Form(...),
    login_code: str = Form(...),
    next_url: str = Form("/me", alias="next"),
    db: Session = Depends(get_db),
) -> Response:
    target = safe_redirect_target(next_url)
    normalized_email = normalize_email(email)
    rate_limit_key = member_login_rate_limit_key(request, "verify", normalized_email)
    retry_after = member_login_verify_limiter.hit(rate_limit_key)
    if retry_after is not None:
        return render_member_login(
            request,
            next_url=target,
            email=normalized_email,
            code_requested=True,
            errors=[rate_limit_message(retry_after)],
            status_code=429,
        )

    member = consume_login_code(db, email=email, code=login_code)
    if member is None:
        return render_member_login(
            request,
            next_url=target,
            email=normalized_email,
            code_requested=True,
            errors=["Enter a valid login code."],
            status_code=403,
        )
    member_login_verify_limiter.reset(rate_limit_key)
    return complete_member_login(db, member=member, target=target)


@router.get("/member-login/verify")
def verify_member_login_link(
    request: Request,
    token: str = Query(...),
    next_url: str = Query("/me", alias="next"),
    db: Session = Depends(get_db),
) -> Response:
    target = safe_redirect_target(next_url)
    token_email = email_for_login_token(db, token=token)
    rate_limit_key = (
        member_login_rate_limit_key(request, "verify", token_email)
        if token_email is not None
        else member_login_token_rate_limit_key(request, "verify", token)
    )

    if not settings.local_login_enabled:
        return render_member_login(
            request,
            next_url=target,
            email=token_email or "",
            errors=["Member login is disabled."],
            status_code=403,
        )

    retry_after = member_login_verify_limiter.hit(rate_limit_key)
    if retry_after is not None:
        return render_member_login(
            request,
            next_url=target,
            email=token_email or "",
            errors=[rate_limit_message(retry_after)],
            status_code=429,
        )

    member = consume_login_token(db, token=token)
    if member is None:
        return render_member_login(
            request,
            next_url=target,
            email=token_email or "",
            errors=["That login link is invalid or expired. Request a new login email."],
            status_code=403,
        )

    member_login_verify_limiter.reset(rate_limit_key)
    return complete_member_login(db, member=member, target=target)


def complete_member_login(db: Session, *, member: Member, target: str) -> Response:
    record_audit(
        db,
        actor=member,
        action="member_login",
        entity_type="member",
        entity_id=member.id,
        summary=f"{member.display_name} logged in as a member.",
    )
    db.commit()
    response = RedirectResponse(target, status_code=303)
    set_session_cookie(response, member)
    return response


@router.get("/me")
def my_profile(member: Member = Depends(require_member)) -> RedirectResponse:
    return RedirectResponse(f"/members/{member.id}", status_code=303)


@router.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/results", status_code=303)
    clear_session_cookie(response)
    return response


def render_login(
    request: Request,
    *,
    next_url: str,
    email: str = "",
    errors: list[str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {
            "next_url": next_url,
            "email": email,
            "errors": errors or [],
            "login_code_required": bool(settings.admin_login_code or settings.admin_setup_code),
        },
        status_code=status_code,
    )


def render_member_login(
    request: Request,
    *,
    next_url: str,
    email: str = "",
    errors: list[str] | None = None,
    summary: str | None = None,
    code_requested: bool = False,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "auth/member_login.html",
        {
            "next_url": next_url,
            "email": email,
            "errors": errors or [],
            "summary": summary,
            "code_requested": code_requested,
        },
        status_code=status_code,
    )


def display_name_from_email(email: str) -> str:
    local_part = email.split("@", maxsplit=1)[0]
    words = local_part.replace(".", " ").replace("_", " ").replace("-", " ").split()
    if not words:
        return email
    return " ".join(word.capitalize() for word in words)


def member_login_rate_limit_key(request: Request, action: str, email: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{action}:{client_host}:{normalize_email(email)}"


def admin_login_rate_limit_key(request: Request, email: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"admin:{client_host}:{normalize_email(email)}"


def member_login_token_rate_limit_key(request: Request, action: str, token: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    token_digest = hashlib.sha256(token.strip().encode()).hexdigest()
    return f"{action}:{client_host}:token:{token_digest}"


def member_login_magic_link(request: Request, *, token: str, next_url: str) -> str:
    base_url = settings.public_base_url.rstrip("/") if settings.public_base_url else str(
        request.base_url
    ).rstrip("/")
    query = urlencode({"token": token, "next": next_url})
    return f"{base_url}/member-login/verify?{query}"


def rate_limit_message(retry_after_seconds: int) -> str:
    minutes = max(1, (retry_after_seconds + 59) // 60)
    return f"Too many login attempts. Try again in about {minutes} minute(s)."


def reset_member_login_rate_limits() -> None:
    admin_login_limiter.clear()
    member_login_request_limiter.clear()
    member_login_verify_limiter.clear()
