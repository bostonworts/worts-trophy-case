"""add member result submissions

Revision ID: 0008_member_result_submissions
Revises: 0007_member_magic_tokens
Create Date: 2026-05-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_member_result_submissions"
down_revision: Union[str, None] = "0007_member_magic_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


placement_scopes = ("'category'", "'best_of_show'")
submission_statuses = ("'pending'", "'approved'", "'rejected'")


def upgrade() -> None:
    op.create_table(
        "member_result_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "member_id",
            sa.Integer(),
            sa.ForeignKey("members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "competition_id",
            sa.Integer(),
            sa.ForeignKey("competitions.id"),
            nullable=False,
        ),
        sa.Column(
            "style_subcategory_id",
            sa.Integer(),
            sa.ForeignKey("style_subcategories.id"),
            nullable=False,
        ),
        sa.Column("bjcp_score", sa.Numeric(4, 1), nullable=True),
        sa.Column("place", sa.Integer(), nullable=True),
        sa.Column("placement_scope", sa.String(length=40), nullable=True),
        sa.Column("recipe_url", sa.String(length=500), nullable=True),
        sa.Column("recipe_file_url", sa.String(length=500), nullable=True),
        sa.Column("photo_url", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="pending", nullable=False),
        sa.Column(
            "reviewed_by_member_id",
            sa.Integer(),
            sa.ForeignKey("members.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "result_id",
            sa.Integer(),
            sa.ForeignKey("results.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "bjcp_score IS NULL OR (bjcp_score > 0 AND bjcp_score <= 50)",
            name="ck_member_result_submissions_bjcp_score",
        ),
        sa.CheckConstraint(
            "place IS NULL OR place BETWEEN 1 AND 4",
            name="ck_member_result_submissions_place",
        ),
        sa.CheckConstraint(
            f"placement_scope IS NULL OR placement_scope IN ({', '.join(placement_scopes)})",
            name="ck_member_result_submissions_placement_scope",
        ),
        sa.CheckConstraint(
            "(place IS NULL AND placement_scope IS NULL) OR "
            "(place IS NOT NULL AND placement_scope IS NOT NULL)",
            name="ck_member_result_submissions_place_scope_pair",
        ),
        sa.CheckConstraint(
            f"status IN ({', '.join(submission_statuses)})",
            name="ck_member_result_submissions_status",
        ),
    )
    op.create_index(
        "ix_member_result_submissions_status",
        "member_result_submissions",
        ["status"],
    )
    op.create_index(
        "ix_member_result_submissions_member_id",
        "member_result_submissions",
        ["member_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_member_result_submissions_member_id",
        table_name="member_result_submissions",
    )
    op.drop_index(
        "ix_member_result_submissions_status",
        table_name="member_result_submissions",
    )
    op.drop_table("member_result_submissions")
