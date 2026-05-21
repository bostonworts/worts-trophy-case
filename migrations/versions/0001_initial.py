"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


competition_types = (
    "'bjcp_sanctioned'",
    "'mcab_qualifier'",
    "'mcab_finals'",
    "'nhc_qualifier'",
    "'nhc_finals'",
    "'club_only'",
    "'other'",
)
placement_scopes = ("'category'", "'best_of_show'")


def upgrade() -> None:
    op.create_table(
        "members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_members_email", "members", ["email"], unique=True)

    op.create_table(
        "competitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("competition_type", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            f"competition_type IN ({', '.join(competition_types)})",
            name="ck_competitions_type",
        ),
        sa.UniqueConstraint("name", "date", name="uq_competitions_name_date"),
    )

    op.create_table(
        "style_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("guide_year", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("guide_year", "code", name="uq_style_categories_year_code"),
    )

    op.create_table(
        "style_subcategories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("style_categories.id"), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("category_id", "code", name="uq_style_subcategories_category_code"),
    )

    op.create_table(
        "results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id"), nullable=False),
        sa.Column("competition_id", sa.Integer(), sa.ForeignKey("competitions.id"), nullable=False),
        sa.Column("style_subcategory_id", sa.Integer(), sa.ForeignKey("style_subcategories.id"), nullable=False),
        sa.Column("bjcp_score", sa.Numeric(4, 1), nullable=True),
        sa.Column("place", sa.Integer(), nullable=True),
        sa.Column("placement_scope", sa.String(length=40), nullable=True),
        sa.Column("recipe_url", sa.String(length=500), nullable=True),
        sa.Column("photo_url", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("bjcp_score IS NULL OR (bjcp_score > 0 AND bjcp_score <= 50)", name="ck_results_bjcp_score"),
        sa.CheckConstraint("place IS NULL OR place BETWEEN 1 AND 4", name="ck_results_place"),
        sa.CheckConstraint(
            f"placement_scope IS NULL OR placement_scope IN ({', '.join(placement_scopes)})",
            name="ck_results_placement_scope",
        ),
        sa.CheckConstraint(
            "(place IS NULL AND placement_scope IS NULL) OR "
            "(place IS NOT NULL AND placement_scope IS NOT NULL)",
            name="ck_results_place_scope_pair",
        ),
    )


def downgrade() -> None:
    op.drop_table("results")
    op.drop_table("style_subcategories")
    op.drop_table("style_categories")
    op.drop_table("competitions")
    op.drop_index("ix_members_email", table_name="members")
    op.drop_table("members")

