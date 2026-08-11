"""世界 AI 对话会话：world_chat_messages 加 session_id（/new 开新会话，旧会话保存可切回）

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-08-11

背景：/new 需要「对话保存、可切回、id 一致」——引入会话概念：
- world_chat_messages.session_id：NULL=默认会话（旧数据兼容），/new 后新会话独立 uuid
- 会话元信息（sessions dict + current_session）存 worlds.config，不建表
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision: str = 'c8d9e0f1a2b3'
down_revision: Union[str, None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('world_chat_messages', sa.Column('session_id', sa.String(32), nullable=True,
                                                   comment='会话 id（NULL=默认会话，/new 后新会话独立）'))
    op.create_index('ix_world_chat_messages_session', 'world_chat_messages', ['world_id', 'session_id'])


def downgrade() -> None:
    op.drop_index('ix_world_chat_messages_session', table_name='world_chat_messages')
    op.drop_column('world_chat_messages', 'session_id')
