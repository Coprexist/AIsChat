"""向量记忆过滤列索引（owner/scope btree）——先缩小范围再向量检索

Revision ID: d5e6f7a8b9c1
Revises: 3e3efdda7d1e
Create Date: 2026-08-15

背景：全站记忆量增长后，向量检索若全表扫再算距离（O(N)）会变慢。
方案（对齐 pgvector 官方过滤策略）：过滤列（owner_id/scope 等）建 btree 索引，
先按结构化字段缩小候选集（O(log N)），再对"自己的"少量记忆做精确向量排序
（O(M log M)，M=单个 owner 的记忆数）——与全站总量 N 解耦。

覆盖 3 张向量表（world_ai_memories 已有 ix_world_ai_memories_world_id）：
- rough_memories:         (owner_id, scope)          检索按 owner+scope 过滤
- detail_memories:        (rough_id)                 按 rough 归属过滤
- group_message_embeddings: (group_id)               按群过滤
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c1'
down_revision: Union[str, None] = '3e3efdda7d1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # rough_memories: 检索 WHERE owner_id=:me AND scope='private' → 先收窄
    op.create_index(
        'idx_rough_owner_scope', 'rough_memories',
        ['owner_id', 'scope'], unique=False,
    )
    # detail_memories: 按 rough 归属过滤（detail 属于某个 rough）
    op.create_index(
        'idx_detail_rough_id', 'detail_memories',
        ['rough_id'], unique=False,
    )
    # group_message_embeddings: 按群过滤（向量检索限本群）
    op.create_index(
        'idx_gme_group', 'group_message_embeddings',
        ['group_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index('idx_gme_group', table_name='group_message_embeddings')
    op.drop_index('idx_detail_rough_id', table_name='detail_memories')
    op.drop_index('idx_rough_owner_scope', table_name='rough_memories')
