"""migrate_offline_to_inactive_agent_state

Revision ID: 1d2a0e12e59f
Revises: a5ceafb69c41
Create Date: 2026-07-26 08:09:14.283805

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1d2a0e12e59f'
down_revision: Union[str, None] = 'a5ceafb69c41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE agents SET state = 'inactive' WHERE state = 'offline'")


def downgrade() -> None:
    op.execute("UPDATE agents SET state = 'offline' WHERE state = 'inactive'")
