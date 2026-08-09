"""AI↔AI 私信限额：agents 加 dm_quota_config / dm_quota_state

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-08-09

背景：AI 之间私信触发接收方 AI 回复（之前 AI→AI 消息只入库不触发）。
为避免互相刷消息烧钱，创建者在配置页设置发送/接收限额：
- dm_quota_config: {"send": {"daily": 20, "weekly": 0, "creator_chat": 0}, "receive": {...}}，0=不启用
- dm_quota_state: 各维度当前计数 + 日历锚点（daily 按天、weekly 按 ISO 周自动重置；创建者发消息时 creator_chat 计数清零）
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from typing import Sequence, Union

revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agents', sa.Column('dm_quota_config', JSONB(), nullable=True,
                                      comment='AI↔AI 私信限额配置: send/receive 各含 daily/weekly/creator_chat 上限（0=不限）'))
    op.add_column('agents', sa.Column('dm_quota_state', JSONB(), nullable=True,
                                      comment='AI↔AI 私信限额计数（日历周期自动重置；创建者发消息时 creator_chat 计数清零）'))


def downgrade() -> None:
    op.drop_column('agents', 'dm_quota_state')
    op.drop_column('agents', 'dm_quota_config')
