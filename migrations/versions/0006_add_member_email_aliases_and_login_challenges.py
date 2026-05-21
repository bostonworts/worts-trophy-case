"""add member email aliases and login challenges

Revision ID: 0006_member_auth
Revises: 0005_add_audit_logs
Create Date: 2026-05-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_member_auth"
down_revision: Union[str, None] = "0005_add_audit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


member_email_kinds = ("'primary'", "'paypal'", "'mailing_list'")


def upgrade() -> None:
    op.add_column(
        "members",
        sa.Column(
            "good_standing",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )

    op.create_table(
        "member_emails",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
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
            f"kind IN ({', '.join(member_email_kinds)})",
            name="ck_member_emails_kind",
        ),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_member_emails_email", "member_emails", ["email"], unique=True)
    op.create_index("ix_member_emails_member_id", "member_emails", ["member_id"])

    op.execute(
        "INSERT INTO member_emails (member_id, email, kind) "
        "SELECT id, email, 'primary' FROM members"
    )

    op.create_table(
        "member_login_challenges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_member_login_challenges_lookup",
        "member_login_challenges",
        ["email", "used_at", "expires_at"],
    )
    op.create_index(
        "ix_member_login_challenges_member_id",
        "member_login_challenges",
        ["member_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_member_login_challenges_member_id", table_name="member_login_challenges")
    op.drop_index("ix_member_login_challenges_lookup", table_name="member_login_challenges")
    op.drop_table("member_login_challenges")
    op.drop_index("ix_member_emails_member_id", table_name="member_emails")
    op.drop_index("ix_member_emails_email", table_name="member_emails")
    op.drop_table("member_emails")
    op.drop_column("members", "good_standing")
