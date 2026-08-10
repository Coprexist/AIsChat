"""世界 AI 结构化记忆表（world_structured_records）：对齐主站 manage_records 目录级键值

Revision ID: b7c8d9e0f1a2
Revises: a8b9c0d1e2f3
Create Date: 2026-08-10

背景：世界 AI 记忆（world_ai_memories）只有 title/content 平铺，且 DeepSeek 无 embedding API
（记忆向量化永远 404 失败，只能靠文本回退）。按珑哥建议对齐主站「结构化记忆」（manage_records）：
- 目录结构 {category}/{sub_key}/{field} → value，纯文本、不依赖 embedding
- UNIQUE(world_id, category, sub_key, field) 实现 upsert
- 工具名与主站一致：manage_records（世界维度命名空间）
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = 'a8b9c0d1e2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'world_structured_records',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('world_id', sa.Integer(), sa.ForeignKey('worlds.id', ondelete='CASCADE'), nullable=False,
                  comment='所属世界'),
        sa.Column('category', sa.String(100), nullable=False, comment='顶层目录名（如 project / setting / knowledge）'),
        sa.Column('sub_key', sa.String(200), nullable=False, comment='子目录名（key，如项目 id / 页面名）'),
        sa.Column('field', sa.String(200), nullable=False, comment='字段名'),
        sa.Column('value', sa.Text(), nullable=False, comment='字段值'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('world_id', 'category', 'sub_key', 'field', name='uq_wsr_path'),
    )
    op.create_index('ix_wsr_world_category', 'world_structured_records', ['world_id', 'category'])


def downgrade() -> None:
    op.drop_index('ix_wsr_world_category', table_name='world_structured_records')
    op.drop_table('world_structured_records')
