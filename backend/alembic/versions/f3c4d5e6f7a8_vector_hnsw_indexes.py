"""向量记忆 HNSW 索引（语义检索加速）

Revision ID: f3c4d5e6f7a8
Revises: f2b3c4d5e6f7
Create Date: 2026-08-08

背景：recall_memory 用 `embedding <=> :q` 余弦距离全表扫描，数据量上来后变慢。
建 pgvector HNSW 索引（vector_cosine_ops）：近似最近邻，毫秒级，无需预聚类。

覆盖：rough_memories / detail_memories / world_ai_memories 的 Vector(1536) 列。
"""
from alembic import op
from typing import Sequence, Union

revision: str = 'f3c4d5e6f7a8'
down_revision: Union[str, None] = 'f2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_rough_memories_embedding_hnsw "
               "ON rough_memories USING hnsw (embedding vector_cosine_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_detail_memories_embedding_hnsw "
               "ON detail_memories USING hnsw (embedding vector_cosine_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_world_ai_memories_embedding_hnsw "
               "ON world_ai_memories USING hnsw (embedding vector_cosine_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_world_ai_memories_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS idx_detail_memories_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS idx_rough_memories_embedding_hnsw")
