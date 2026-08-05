"""recreate dropped tables (structured_records / agent_workspace / agent_alarms)

事故恢复：ab0d1f883cee（autogenerate 垃圾输出）误删了三个表。
这些表的模型存在但未注册进 app/models/__init__.py，autogenerate 把它们当"该删的表"。
已补注册（根因修复），本迁移按模型定义重建三表。

注意：历史数据无法恢复（无备份），重建后为空表。

Revision ID: c2d3e4f5a6b7
Revises: ab0d1f883cee
Create Date: 2026-08-04 08:50:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'ab0d1f883cee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 与 models/alarm.py 一致：AI 自主闹钟
    op.create_table('agent_alarms',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('wake_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('task', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('fired_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status::text = ANY (ARRAY['pending'::character varying, 'fired'::character varying, 'cancelled'::character varying]::text[])",
            name='agent_alarms_status_check'
        ),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # 与 models/workspace.py 一致：AI 当前任务追踪 / 中断恢复
    op.create_table('agent_workspace',
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('current_task', sa.Text(), nullable=True),
        sa.Column('current_task_at', sa.DateTime(), nullable=True),
        sa.Column('interrupted_at', sa.DateTime(), nullable=True),
        sa.Column('interruption_reason', sa.Text(), nullable=True),
        sa.Column('todo', sa.Text(), server_default=''),
        sa.Column('plan', sa.Text(), server_default=''),
        sa.Column('journal', sa.Text(), server_default=''),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('agent_id'),
    )

    # 与 models/structured_record.py 一致：AI 结构化记忆
    op.create_table('structured_records',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('sub_key', sa.String(200), nullable=False),
        sa.Column('field', sa.String(200), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('agent_id', 'category', 'sub_key', 'field', name='uq_sr_path'),
    )


def downgrade() -> None:
    op.drop_table('structured_records')
    op.drop_table('agent_workspace')
    op.drop_table('agent_alarms')
