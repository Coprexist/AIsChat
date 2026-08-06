"""capability_versions table + agents 能力懒加载版本字段

skills/tools 版本化（平台 + 世界统一）：每个能力源一条版本链，
content_hash 变化 → 新版本（definitions 快照 + changelog），旧版本保留；
agents 记录 known（告知进度）/ effective（生效进度），compact 时切最新。

Revision ID: b5c6d7e8f9a0
Revises: a3b4c5d6e7f8
Create Date: 2026-08-06 11:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'b5c6d7e8f9a0'
down_revision: Union[str, None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'capability_versions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('source', sa.String(50), nullable=False, comment='能力源：platform / world-{id}'),
        sa.Column('version', sa.Integer(), nullable=False, comment='版本号（每源内递增）'),
        sa.Column('content_hash', sa.String(64), nullable=False, comment='源内容哈希（检测变更）'),
        sa.Column('changelog', sa.Text(), default='', comment='本版本变更摘要（增量注入用）'),
        sa.Column('definitions', JSONB(), nullable=True, comment='工具定义快照'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('source', 'version', name='uq_capability_ver_source_version'),
    )
    op.create_index('ix_capability_versions_source', 'capability_versions', ['source'])
    op.add_column('agents', sa.Column('cap_known_versions', JSONB(), nullable=True, comment='能力源告知进度 {source: version}'))
    op.add_column('agents', sa.Column('cap_effective_versions', JSONB(), nullable=True, comment='能力源生效进度 {source: version}'))


def downgrade() -> None:
    op.drop_column('agents', 'cap_effective_versions')
    op.drop_column('agents', 'cap_known_versions')
    op.drop_index('ix_capability_versions_source', table_name='capability_versions')
    op.drop_table('capability_versions')
