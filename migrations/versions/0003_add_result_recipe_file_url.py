"""add result recipe file url

Revision ID: 0003_add_result_recipe_file_url
Revises: 0002_add_archive_timestamps
Create Date: 2026-05-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_add_result_recipe_file_url"
down_revision: Union[str, None] = "0002_add_archive_timestamps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "results",
        sa.Column("recipe_file_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("results", "recipe_file_url")
