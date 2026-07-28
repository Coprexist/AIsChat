"""add_registration_enabled_to_system_settings

Revision ID: b3c4d5e6f7g8
Revises: 7417befe2eba
Create Date: 2026-07-28 11:02:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7g8'
down_revision: Union[str, None] = '7417befe2eba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS "
        "registration_enabled BOOLEAN DEFAULT TRUE"
    )
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS "
        "geoip_provider_url VARCHAR(512)"
    )


def downgrade() -> None:
    op.drop_column("system_settings", "registration_enabled")
    op.drop_column("system_settings", "geoip_provider_url")
