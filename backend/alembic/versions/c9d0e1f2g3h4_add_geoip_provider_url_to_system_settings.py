"""add_geoip_provider_url_to_system_settings

Revision ID: c9d0e1f2g3h4
Revises: b3c4d5e6f7g8
Create Date: 2026-07-28 11:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d0e1f2g3h4'
down_revision: Union[str, None] = 'b3c4d5e6f7g8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS "
        "geoip_provider_url VARCHAR(512)"
    )


def downgrade() -> None:
    op.drop_column("system_settings", "geoip_provider_url")
