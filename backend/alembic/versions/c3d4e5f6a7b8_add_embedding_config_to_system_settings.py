"""system_settings + embedding_config 列（DB 覆盖 env 的图形化配置）

Revision ID: c3d4e5f6a7b8
Revises: d5e6f7a8b9c1
Create Date: 2026-08-15

Embedding 提供方配置存 DB（管理员前端图形化修改，覆盖 EMBEDDING_* 环境变量）。
结构: {backend, base_url, api_key_encrypted, model, dimension, enabled}

用 IF NOT EXISTS 幂等：生产库可能已通过旧 migration.py 加过该列。
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'd5e6f7a8b9c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS "
        "embedding_config JSONB"
    )


def downgrade() -> None:
    op.drop_column("system_settings", "embedding_config")
