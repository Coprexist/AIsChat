"""add_last_active_at_to_users

Revision ID: 7417befe2eba
Revises: 1d2a0e12e59f
Create Date: 2026-07-26 09:39:23.141916

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7417befe2eba'
down_revision: Union[str, None] = '1d2a0e12e59f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMP WITH TIME ZONE")


def downgrade() -> None:
    op.drop_column("users", "last_active_at")
