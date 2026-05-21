from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AppSetting(TimestampMixin, Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(String(500), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    actor_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("members.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(nullable=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    actor: Mapped[Member | None] = relationship()


class CompetitionType(str, enum.Enum):
    BJCP_SANCTIONED = "bjcp_sanctioned"
    MCAB_QUALIFIER = "mcab_qualifier"
    MCAB_FINALS = "mcab_finals"
    NHC_QUALIFIER = "nhc_qualifier"
    NHC_FINALS = "nhc_finals"
    CLUB_ONLY = "club_only"
    OTHER = "other"


class PlacementScope(str, enum.Enum):
    CATEGORY = "category"
    BEST_OF_SHOW = "best_of_show"


class MemberEmailKind(str, enum.Enum):
    PRIMARY = "primary"
    PAYPAL = "paypal"
    MAILING_LIST = "mailing_list"


def enum_values(enum_class: type[enum.Enum]) -> list[str]:
    return [item.value for item in enum_class]


class Member(TimestampMixin, Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_admin: Mapped[bool] = mapped_column(default=False, nullable=False)
    good_standing: Mapped[bool] = mapped_column(default=True, nullable=False)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    results: Mapped[list[Result]] = relationship(back_populates="member")
    emails: Mapped[list[MemberEmail]] = relationship(
        back_populates="member",
        cascade="all, delete-orphan",
    )


class MemberEmail(TimestampMixin, Base):
    __tablename__ = "member_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    kind: Mapped[MemberEmailKind] = mapped_column(
        SAEnum(
            MemberEmailKind,
            values_callable=enum_values,
            native_enum=False,
            name="member_email_kind",
        ),
        nullable=False,
    )

    member: Mapped[Member] = relationship(back_populates="emails")


class MemberLoginChallenge(Base):
    __tablename__ = "member_login_challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    token_hash: Mapped[str | None] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    member: Mapped[Member] = relationship()


class Competition(TimestampMixin, Base):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    competition_type: Mapped[CompetitionType] = mapped_column(
        SAEnum(
            CompetitionType,
            values_callable=enum_values,
            native_enum=False,
            name="competition_type",
        ),
        nullable=False,
    )

    results: Mapped[list[Result]] = relationship(back_populates="competition")

    __table_args__ = (
        UniqueConstraint("name", "date", name="uq_competitions_name_date"),
    )


class StyleCategory(TimestampMixin, Base):
    __tablename__ = "style_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    guide_year: Mapped[int] = mapped_column(nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    subcategories: Mapped[list[StyleSubcategory]] = relationship(back_populates="category")

    __table_args__ = (
        UniqueConstraint("guide_year", "code", name="uq_style_categories_year_code"),
    )


class StyleSubcategory(TimestampMixin, Base):
    __tablename__ = "style_subcategories"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("style_categories.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    category: Mapped[StyleCategory] = relationship(back_populates="subcategories")
    results: Mapped[list[Result]] = relationship(back_populates="style_subcategory")

    __table_args__ = (
        UniqueConstraint("category_id", "code", name="uq_style_subcategories_category_code"),
    )


class Result(TimestampMixin, Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"), nullable=False)
    style_subcategory_id: Mapped[int] = mapped_column(
        ForeignKey("style_subcategories.id"),
        nullable=False,
    )
    bjcp_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    place: Mapped[int | None] = mapped_column(nullable=True)
    placement_scope: Mapped[PlacementScope | None] = mapped_column(
        SAEnum(
            PlacementScope,
            values_callable=enum_values,
            native_enum=False,
            name="placement_scope",
        ),
        nullable=True,
    )
    recipe_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recipe_file_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    member: Mapped[Member] = relationship(back_populates="results")
    competition: Mapped[Competition] = relationship(back_populates="results")
    style_subcategory: Mapped[StyleSubcategory] = relationship(back_populates="results")

    __table_args__ = (
        CheckConstraint(
            "bjcp_score IS NULL OR (bjcp_score > 0 AND bjcp_score <= 50)",
            name="ck_results_bjcp_score",
        ),
        CheckConstraint("place IS NULL OR place BETWEEN 1 AND 4", name="ck_results_place"),
        CheckConstraint(
            "(place IS NULL AND placement_scope IS NULL) OR "
            "(place IS NOT NULL AND placement_scope IS NOT NULL)",
            name="ck_results_place_scope_pair",
        ),
    )
