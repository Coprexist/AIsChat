"""add_audit_user_actions_to_system_settings

Revision ID: d0e1f2g3h4i5
Revises: c9d0e1f2g3h4
Create Date: 2026-07-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd0e1f2g3h4i5'
down_revision: Union[str, None] = 'c9d0e1f2g3h4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS "
        "audit_user_actions BOOLEAN DEFAULT FALSE"
    )


def downgrade() -> None:
    op.drop_column("system_settings", "audit_user_actions")
