"""world ai config and chat

群视界机器人 = 世界配置（worlds.creator_config / creator_notices），非 agent、无账号。
world_chat_messages = 世界 AI 对话（世界级会话，非 DM）。

注意：本迁移已人工审改——autogenerate 原始输出含大量误删（structured_records /
agent_workspace / agent_alarms 等模型未注册 __init__ 导致的假 diff），已全部剔除。
三表由后续迁移 c2d3e4f5a6b7 重建。

Revision ID: ab0d1f883cee
Revises: c0c1c2c3c4c5
Create Date: 2026-08-04 08:42:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ab0d1f883cee'
down_revision: Union[str, None] = 'c0c1c2c3c4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 世界 AI 对话表（世界级会话）
    op.create_table('world_chat_messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('world_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True, comment='发言用户（AI 消息为 Null）'),
        sa.Column('role', sa.String(length=10), nullable=False, comment='user | ai'),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['world_id'], ['worlds.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # 群视界机器人 = 世界配置（非 agent、无账号）
    op.add_column('worlds', sa.Column('creator_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='群视界机器人配置 {name, system_prompt, model, temperature, top_p, tools}'))
    op.add_column('worlds', sa.Column('creator_notices', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='代码改动懒通知 [{file, location, summary, at}]（用户改代码→下次对话附送）'))


def downgrade() -> None:
    op.drop_column('worlds', 'creator_notices')
    op.drop_column('worlds', 'creator_config')
    op.drop_table('world_chat_messages')
