"""add_message_retention_days_to_system_settings

Revision ID: f0g1h2i3j4k5
Revises: e0f1g2h3i4j5
Create Date: 2026-07-28 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f0g1h2i3j4k5'
down_revision: Union[str, None] = 'e0f1g2h3i4j5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS "
        "message_retention_days INTEGER DEFAULT 0"
    )


def downgrade() -> None:
    op.drop_column("system_settings", "message_retention_days")
