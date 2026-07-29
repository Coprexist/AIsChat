"""add group avatar settings (avatar_mode, avatar_url, include_ai_in_avatar)

Revision ID: a0b1c2d3e4f5
Revises: 1ed66a7072ff
Create Date: 2026-07-29 08:48:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a0b1c2d3e4f5'
down_revision: Union[str, None] = '1ed66a7072ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "groups",
        sa.Column("avatar_mode", sa.String(20), server_default="default", nullable=False),
    )
    op.add_column(
        "groups",
        sa.Column("avatar_url", sa.String(500), nullable=True),
    )
    op.add_column(
        "groups",
        sa.Column("include_ai_in_avatar", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("groups", "include_ai_in_avatar")
    op.drop_column("groups", "avatar_url")
    op.drop_column("groups", "avatar_mode")
