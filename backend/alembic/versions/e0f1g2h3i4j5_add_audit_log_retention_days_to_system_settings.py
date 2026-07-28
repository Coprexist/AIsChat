"""add_audit_log_retention_days_to_system_settings

Revision ID: e0f1g2h3i4j5
Revises: d0e1f2g3h4i5
Create Date: 2026-07-28 12:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e0f1g2h3i4j5'
down_revision: Union[str, None] = 'd0e1f2g3h4i5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS "
        "audit_log_retention_days INTEGER DEFAULT 90"
    )


def downgrade() -> None:
    op.drop_column("system_settings", "audit_log_retention_days")
