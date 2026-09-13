"""world_chat_messages add attachments column

群视界支持发图：用户消息携带附件。图片会经 app/utils/multimodal.py 转成
OpenAI 多模态 content 注入 LLM（唯一入口，主站聊天共用同一实现）。

Revision ID: e8f9a0b1c2d3
Revises: d2e3f4a5b6c7
Create Date: 2026-09-13 14:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('world_chat_messages', sa.Column(
        'attachments', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
        comment='消息附件 [{file_id, path, name, size, mime_type}]（2026-09-13 新增）',
    ))


def downgrade() -> None:
    op.drop_column('world_chat_messages', 'attachments')
