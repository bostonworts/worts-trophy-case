from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from secrets import randbelow, token_urlsafe
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Member, MemberEmail, MemberEmailKind, MemberLoginChallenge


LOGIN_CODE_TTL_MINUTES = 15


class LoginChallenge(NamedTuple):
    code: str
    magic_token: str


def normalize_email(value: str) -> str:
    return value.strip().lower()


def member_for_login_email(db: Session, email: str) -> Member | None:
    normalized = normalize_email(email)
    member = db.scalar(
        select(Member)
        .join(MemberEmail, MemberEmail.member_id == Member.id)
        .where(MemberEmail.email == normalized)
    )
    if member is not None:
        return member
    return db.scalar(select(Member).where(Member.email == normalized))


def eligible_member_for_login_email(db: Session, email: str) -> Member | None:
    member = member_for_login_email(db, email)
    if member is None or member.deactivated_at is not None or not member.good_standing:
        return None
    return member


def issue_login_code(db: Session, *, member: Member, email: str) -> str:
    return issue_login_challenge(db, member=member, email=email).code


def issue_login_challenge(db: Session, *, member: Member, email: str) -> LoginChallenge:
    normalized = normalize_email(email)
    code = f"{randbelow(1_000_000):06d}"
    magic_token = token_urlsafe(32)
    db.add(
        MemberLoginChallenge(
            member_id=member.id,
            email=normalized,
            code_hash=hash_login_code(code),
            token_hash=hash_login_token(magic_token),
            expires_at=datetime.now(UTC) + timedelta(minutes=LOGIN_CODE_TTL_MINUTES),
        )
    )
    return LoginChallenge(code=code, magic_token=magic_token)


def ensure_primary_email_alias(db: Session, member: Member) -> None:
    normalized = normalize_email(member.email)
    existing_for_email = db.scalar(
        select(MemberEmail).where(MemberEmail.email == normalized).limit(1)
    )
    existing_primary = db.scalar(
        select(MemberEmail).where(
            MemberEmail.member_id == member.id,
            MemberEmail.kind == MemberEmailKind.PRIMARY,
        )
    )

    if existing_for_email is not None:
        if existing_for_email.member_id != member.id:
            raise ValueError("Email is already attached to another member.")
        if existing_primary is not None and existing_primary.id != existing_for_email.id:
            db.delete(existing_for_email)
            db.flush()
            existing_primary.email = normalized
            return
        existing_for_email.kind = MemberEmailKind.PRIMARY
        return

    if existing_primary is None:
        db.add(MemberEmail(member_id=member.id, kind=MemberEmailKind.PRIMARY, email=normalized))
    else:
        existing_primary.email = normalized


def consume_login_code(db: Session, *, email: str, code: str) -> Member | None:
    normalized = normalize_email(email)
    member = eligible_member_for_login_email(db, normalized)
    if member is None:
        return None

    now = datetime.now(UTC)
    challenges = db.scalars(
        select(MemberLoginChallenge)
        .where(
            MemberLoginChallenge.member_id == member.id,
            MemberLoginChallenge.email == normalized,
            MemberLoginChallenge.used_at.is_(None),
            MemberLoginChallenge.expires_at > now,
        )
        .order_by(MemberLoginChallenge.created_at.desc(), MemberLoginChallenge.id.desc())
        .limit(5)
    ).all()
    code_hash = hash_login_code(code.strip())
    for challenge in challenges:
        if hmac.compare_digest(challenge.code_hash, code_hash):
            challenge.used_at = now
            return member
    return None


def email_for_login_token(db: Session, *, token: str) -> str | None:
    token_hash = hash_login_token(token)
    if token_hash is None:
        return None
    return db.scalar(
        select(MemberLoginChallenge.email)
        .where(MemberLoginChallenge.token_hash == token_hash)
        .limit(1)
    )


def consume_login_token(db: Session, *, token: str) -> Member | None:
    token_hash = hash_login_token(token)
    if token_hash is None:
        return None

    now = datetime.now(UTC)
    challenge = db.scalar(
        select(MemberLoginChallenge)
        .where(
            MemberLoginChallenge.token_hash == token_hash,
            MemberLoginChallenge.used_at.is_(None),
            MemberLoginChallenge.expires_at > now,
        )
        .limit(1)
    )
    if challenge is None:
        return None

    member = eligible_member_for_login_email(db, challenge.email)
    if member is None or member.id != challenge.member_id:
        return None

    challenge.used_at = now
    return member


def email_in_use_by_other_member(
    db: Session,
    email: str,
    *,
    exclude_member_id: int | None = None,
) -> bool:
    normalized = normalize_email(email)
    member_statement = select(Member.id).where(Member.email == normalized)
    alias_statement = select(MemberEmail.member_id).where(MemberEmail.email == normalized)
    if exclude_member_id is not None:
        member_statement = member_statement.where(Member.id != exclude_member_id)
        alias_statement = alias_statement.where(MemberEmail.member_id != exclude_member_id)
    return db.scalar(member_statement.limit(1)) is not None or db.scalar(
        alias_statement.limit(1)
    ) is not None


def member_with_any_email(db: Session, emails: list[str]) -> Member | None:
    normalized_emails = [normalize_email(email) for email in emails if normalize_email(email)]
    if not normalized_emails:
        return None
    member = db.scalar(select(Member).where(Member.email.in_(normalized_emails)).limit(1))
    if member is not None:
        return member
    alias_member_id = db.scalar(
        select(MemberEmail.member_id).where(MemberEmail.email.in_(normalized_emails)).limit(1)
    )
    return db.get(Member, alias_member_id) if alias_member_id is not None else None


def hash_login_code(code: str) -> str:
    value = f"{settings.app_secret_key}:{code}".encode()
    return hashlib.sha256(value).hexdigest()


def hash_login_token(token: str) -> str | None:
    normalized = token.strip()
    if not normalized:
        return None
    value = f"{settings.app_secret_key}:member-login-token:{normalized}".encode()
    return hashlib.sha256(value).hexdigest()
