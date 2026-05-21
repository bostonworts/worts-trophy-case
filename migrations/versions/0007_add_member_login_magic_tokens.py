"""add member login magic tokens

Revision ID: 0007_member_magic_tokens
Revises: 0006_member_auth
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_member_magic_tokens"
down_revision: Union[str, None] = "0006_member_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "member_login_challenges",
        sa.Column("token_hash", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_member_login_challenges_token_hash",
        "member_login_challenges",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_member_login_challenges_token_hash", table_name="member_login_challenges")
    op.drop_column("member_login_challenges", "token_hash")
