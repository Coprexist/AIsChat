"""align column comments (agent_alarms / agent_workspace)

噪音修复：重建的三表缺列注释（模型有、DB 无），导致 autogenerate 每次报 modify_comment。
一次性补齐注释，之后 alembic check 应干净。

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-04 09:10:00

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COMMENTS = [
    ("agent_alarms", "wake_at", "唤醒时间"),
    ("agent_alarms", "task", "唤醒后要执行的任务描述"),
    ("agent_alarms", "status", "pending / fired / cancelled"),
    ("agent_alarms", "fired_at", "实际触发时间"),
    ("agent_workspace", "current_task", "AI 当前正在做的任务描述"),
    ("agent_workspace", "current_task_at", "任务开始时间"),
    ("agent_workspace", "interrupted_at", "被中断的时间"),
    ("agent_workspace", "interruption_reason", "中断原因（谁发消息打断了）"),
    ("agent_workspace", "updated_at", "最后更新时间"),
    ("agent_workspace", "todo", "AI 的 TODO 列表（markdown）"),
    ("agent_workspace", "plan", "AI 的 PLAN 规划（markdown）"),
    ("agent_workspace", "journal", "AI 的 JOURNAL 日志（markdown，按日期追加）"),
]


def upgrade() -> None:
    for table, col, comment in _COMMENTS:
        op.execute(f"COMMENT ON COLUMN {table}.{col} IS '{comment}'")


def downgrade() -> None:
    for table, col, _ in _COMMENTS:
        op.execute(f"COMMENT ON COLUMN {table}.{col} IS NULL")
