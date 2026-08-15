"""system_settings + runtime_config 列（运行时参数前端图形化）

Revision ID: e6f7a8b9c0d2
Revises: c3d4e5f6a7b8
Create Date: 2026-08-15

运行时参数组（检索 top_k/权重、显示时区、摘要 TTL）DB 覆盖 env，
管理员前端图形化修改，热更新无需重启。
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e6f7a8b9c0d2'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS runtime_config JSONB"
    )


def downgrade() -> None:
    op.drop_column("system_settings", "runtime_config")
