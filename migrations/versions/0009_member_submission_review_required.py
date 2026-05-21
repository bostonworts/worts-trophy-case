"""add member submission review flag

Revision ID: 0009_member_review_required
Revises: 0008_member_result_submissions
Create Date: 2026-05-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_member_review_required"
down_revision: Union[str, None] = "0008_member_result_submissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "members",
        sa.Column(
            "submission_review_required",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("members", "submission_review_required")
