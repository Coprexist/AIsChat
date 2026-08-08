"""AI 情感向量化配置

Revision ID: f4d5e6f7a8b9
Revises: f3c4d5e6f7a8
Create Date: 2026-08-08

- agents 加 emotion_vectorized（勾选后情感向量化更拟人；不勾退回文字心情描述）
- agents 加 llm_call_count（AI 调用总次数，记忆/情感衰减的时间尺度）
- 状态帧情感/工具隔离字段在 agents.state_stack JSONB 内扩展，无需迁移
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision: str = 'f4d5e6f7a8b9'
down_revision: Union[str, None] = 'f3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agents', sa.Column('emotion_vectorized', sa.Boolean(), nullable=False,
                                      server_default=sa.text('false'),
                                      comment='向量化情感（更拟人）；不勾退回文字心情描述'))
    op.add_column('agents', sa.Column('llm_call_count', sa.Integer(), nullable=False,
                                      server_default=sa.text('0'),
                                      comment='AI 调用总次数（记忆/情感衰减时间尺度）'))


def downgrade() -> None:
    op.drop_column('agents', 'llm_call_count')
    op.drop_column('agents', 'emotion_vectorized')
