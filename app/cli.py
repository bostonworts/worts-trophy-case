from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    AppSetting,
    AuditLog,
    Competition,
    CompetitionType,
    Member,
    MemberEmail,
    MemberEmailKind,
    MemberLoginChallenge,
    PlacementScope,
    Result,
    StyleSubcategory,
)
from app.db.session import SessionLocal
from app.routers.admin import build_backup_payload, restore_backup_payload
from app.services.member_auth import ensure_primary_email_alias, member_with_any_email
from app.services.styleguide_importer import import_styleguide


def seed() -> None:
    with SessionLocal() as db:
        import_result = import_styleguide(db)

        members = [
            member(
                db,
                email="demo-admin@example.test",
                display_name="Demo Admin",
                is_admin=True,
            ),
            member(
                db,
                email="alex-list@example.test",
                display_name="Alex Rivera",
                paypal_email="alex-paypal@example.test",
                mailing_list_email="alex-list@example.test",
            ),
            member(
                db,
                email="jordan-list@example.test",
                display_name="Jordan Kim",
                paypal_email="jordan-paypal@example.test",
                mailing_list_email="jordan-list@example.test",
            ),
            member(
                db,
                email="casey-list@example.test",
                display_name="Casey Stone",
                paypal_email="casey-paypal@example.test",
                mailing_list_email="casey-list@example.test",
            ),
            member(
                db,
                email="lapsed-list@example.test",
                display_name="Lapsed Member",
                paypal_email="lapsed-paypal@example.test",
                mailing_list_email="lapsed-list@example.test",
                good_standing=False,
            ),
        ]

        american_ipa = style_subcategory(db, code="21A")
        hazy_ipa = style_subcategory(db, code="21C")
        american_stout = style_subcategory(db, code="20B")

        bluebonnet = competition(
            db,
            name="Bluebonnet Brew-Off",
            date_=date(2026, 3, 21),
            url="https://example.test/bluebonnet",
            competition_type=CompetitionType.BJCP_SANCTIONED,
        )
        nhc = competition(
            db,
            name="National Homebrew Competition",
            date_=date(2026, 5, 7),
            url="https://example.test/nhc",
            competition_type=CompetitionType.NHC_QUALIFIER,
        )
        club = competition(
            db,
            name="Worts Club Challenge",
            date_=date(2026, 4, 11),
            url=None,
            competition_type=CompetitionType.CLUB_ONLY,
        )

        result(
            db,
            member=members[1],
            competition=bluebonnet,
            style_subcategory=american_ipa,
            bjcp_score=Decimal("39.0"),
            place=1,
            placement_scope=PlacementScope.CATEGORY,
            recipe_url="https://example.test/recipes/american-ipa",
        )
        result(
            db,
            member=members[2],
            competition=nhc,
            style_subcategory=hazy_ipa,
            bjcp_score=Decimal("41.0"),
            place=2,
            placement_scope=PlacementScope.BEST_OF_SHOW,
            recipe_url=None,
        )
        result(
            db,
            member=members[3],
            competition=club,
            style_subcategory=american_stout,
            bjcp_score=Decimal("36.0"),
            place=1,
            placement_scope=PlacementScope.CATEGORY,
            recipe_url=None,
        )

        db.commit()
        print(
            "Seed data loaded "
            f"with {import_result.categories_total} categories and "
            f"{import_result.subcategories_total} subcategories."
        )
        print("Demo admin: demo-admin@example.test")
        print("Demo member login: alex-list@example.test")
        print("Lapsed member for negative tests: lapsed-list@example.test")


def load_styles() -> None:
    with SessionLocal() as db:
        import_result = import_styleguide(db)
        db.commit()
        print(
            f"Imported {import_result.categories_seen} categories and "
            f"{import_result.subcategories_seen} subcategories. "
            f"Database now has {import_result.categories_total} categories and "
            f"{import_result.subcategories_total} subcategories."
        )


def backup(output: str) -> None:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        output_path.write_text(
            json.dumps(build_backup_payload(db), indent=2),
            encoding="utf-8",
        )
    print(f"Wrote backup to {output_path}.")


def restore(input_path: str) -> None:
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    with SessionLocal() as db:
        summary, errors = restore_backup_payload(db, payload)
        if errors:
            raise RuntimeError("; ".join(errors))
        db.commit()
    print(summary)


def reset_data(confirm: str) -> None:
    if confirm != "RESET_DATA":
        raise RuntimeError("Pass --confirm RESET_DATA to reset local data.")
    with SessionLocal() as db:
        db.execute(delete(AuditLog))
        db.execute(delete(Result))
        db.execute(delete(Competition))
        db.execute(delete(MemberLoginChallenge))
        db.execute(delete(MemberEmail))
        db.execute(delete(Member))
        db.execute(delete(AppSetting))
        db.commit()
    print("Deleted members, competitions, results, audit logs, and app settings.")


def member(
    db: Session,
    *,
    email: str,
    display_name: str,
    paypal_email: str | None = None,
    mailing_list_email: str | None = None,
    is_admin: bool = False,
    good_standing: bool = True,
) -> Member:
    existing = member_with_any_email(
        db,
        [
            email,
            paypal_email or "",
            mailing_list_email or "",
        ],
    )
    if existing:
        existing.email = email
        existing.display_name = display_name
        existing.is_admin = is_admin
        existing.good_standing = good_standing
        sync_seed_member_email_aliases(
            db,
            existing,
            paypal_email=paypal_email,
            mailing_list_email=mailing_list_email,
        )
        return existing
    value = Member(
        email=email,
        display_name=display_name,
        is_admin=is_admin,
        good_standing=good_standing,
    )
    db.add(value)
    db.flush()
    sync_seed_member_email_aliases(
        db,
        value,
        paypal_email=paypal_email,
        mailing_list_email=mailing_list_email,
    )
    return value


def sync_seed_member_email_aliases(
    db: Session,
    value: Member,
    *,
    paypal_email: str | None,
    mailing_list_email: str | None,
) -> None:
    ensure_primary_email_alias(db, value)
    sync_seed_member_email(db, value, MemberEmailKind.PAYPAL, paypal_email)
    sync_seed_member_email(db, value, MemberEmailKind.MAILING_LIST, mailing_list_email)


def sync_seed_member_email(
    db: Session,
    value: Member,
    kind: MemberEmailKind,
    email: str | None,
) -> None:
    normalized_email = (email or "").strip().lower()
    existing = db.scalar(
        select(MemberEmail).where(
            MemberEmail.member_id == value.id,
            MemberEmail.kind == kind,
        )
    )
    if not normalized_email or normalized_email == value.email:
        if existing is not None:
            db.delete(existing)
        return
    if existing is None:
        db.add(MemberEmail(member=value, kind=kind, email=normalized_email))
    else:
        existing.email = normalized_email


def style_subcategory(db: Session, *, code: str) -> StyleSubcategory:
    subcategory = db.scalar(select(StyleSubcategory).where(StyleSubcategory.code == code))
    if subcategory is None:
        raise RuntimeError(
            f"Missing style subcategory {code}. Run `python -m app.cli load-styles`."
        )
    return subcategory


def competition(
    db: Session,
    *,
    name: str,
    date_: date,
    url: str | None,
    competition_type: CompetitionType,
) -> Competition:
    existing = db.scalar(
        select(Competition).where(
            Competition.name == name,
            Competition.date == date_,
        )
    )
    if existing:
        return existing
    value = Competition(name=name, date=date_, url=url, competition_type=competition_type)
    db.add(value)
    db.flush()
    return value


def result(
    db: Session,
    *,
    member: Member,
    competition: Competition,
    style_subcategory: StyleSubcategory,
    bjcp_score: Decimal,
    place: int | None,
    placement_scope: PlacementScope | None,
    recipe_url: str | None,
) -> Result:
    existing = db.scalar(
        select(Result).where(
            Result.member_id == member.id,
            Result.competition_id == competition.id,
            Result.style_subcategory_id == style_subcategory.id,
            Result.place == place,
            Result.placement_scope == placement_scope,
        )
    )
    if existing:
        return existing
    value = Result(
        member=member,
        competition=competition,
        style_subcategory=style_subcategory,
        bjcp_score=bjcp_score,
        place=place,
        placement_scope=placement_scope,
        recipe_url=recipe_url,
    )
    db.add(value)
    db.flush()
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("load-styles")
    subparsers.add_parser("seed")

    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("--output", default="/uploads/backups/trophy-case-backup.json")

    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("input_path")

    reset_parser = subparsers.add_parser("reset-data")
    reset_parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    if args.command == "seed":
        seed()
    elif args.command == "load-styles":
        load_styles()
    elif args.command == "backup":
        backup(args.output)
    elif args.command == "restore":
        restore(args.input_path)
    elif args.command == "reset-data":
        reset_data(args.confirm)


if __name__ == "__main__":
    main()
