"""用户 GitHub 账户绑定（商城同步以用户身份推送）

Revision ID: f1a2b3c4d5e6
Revises: e4f5a6b7c8d9
Create Date: 2026-08-08

- users 加 github_token_encrypted（加密存储）+ github_username（绑定时的 GitHub 用户名）
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('github_token_encrypted', sa.Text(), nullable=True,
                                     comment='用户 GitHub token（加密）'))
    op.add_column('users', sa.Column('github_username', sa.String(100), nullable=True,
                                     comment='绑定时的 GitHub 用户名'))


def downgrade() -> None:
    op.drop_column('users', 'github_username')
    op.drop_column('users', 'github_token_encrypted')
