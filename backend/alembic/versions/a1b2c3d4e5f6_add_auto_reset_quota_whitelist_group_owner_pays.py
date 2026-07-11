"""add auto_reset_quota, quota_whitelist, group_owner_pays

Revision ID: a1b2c3d4e5f6
Revises: fbb403b42c46
Create Date: 2026-07-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'fbb403b42c46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 新增 auto_reset_quota 列
    op.add_column('agents', sa.Column('auto_reset_quota', sa.Boolean(),
        nullable=False, server_default=sa.text('false'),
        comment="每次用户 DM 时自动重置配额计数"))

    # 2. 新增 quota_whitelist 列（JSONB 数组）
    op.add_column('agents', sa.Column('quota_whitelist', JSONB,
        nullable=False, server_default=sa.text("'[]'::jsonb"),
        comment="不消耗配额的白名单实体列表"))

    # 3. 新增 group_owner_pays 列
    op.add_column('agents', sa.Column('group_owner_pays', sa.Boolean(),
        nullable=False, server_default=sa.text('true'),
        comment="群聊中 AI 消息是否由群主付费"))

    # 4. 强制迁移：所有 allow_others_chat=true 且 others_chat_mode='unlimited'
    #    的 AI 切换到 quota 模式，配额根据 AI 类型动态设定
    op.execute("""
        UPDATE agents
        SET others_chat_mode = 'quota',
            others_chat_quota = CASE ai_type
                WHEN 'general' THEN 50
                WHEN 'semi_general' THEN 30
                ELSE 10
            END
        WHERE allow_others_chat = true
          AND others_chat_mode = 'unlimited'
    """)


def downgrade() -> None:
    op.drop_column('agents', 'group_owner_pays')
    op.drop_column('agents', 'quota_whitelist')
    op.drop_column('agents', 'auto_reset_quota')
