"""GitHub 身份锚与作者签名（跨实例归属）

Revision ID: f2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-08-08

- users 加 github_id（数字 ID，改名不变——身份锚）
- users 加 github_sign_key_encrypted（Ed25519 私钥，加密存储——作者签名用）
- users 加 github_public_key（Ed25519 公钥，随 meta 发布供验签）
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision: str = 'f2b3c4d5e6f7'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('github_id', sa.BigInteger(), nullable=True,
                                     comment='GitHub 数字 user id（身份锚，改名不变）'))
    op.add_column('users', sa.Column('github_sign_key_encrypted', sa.Text(), nullable=True,
                                     comment='Ed25519 私钥（加密存储，作者签名用）'))
    op.add_column('users', sa.Column('github_public_key', sa.Text(), nullable=True,
                                     comment='Ed25519 公钥（随 meta 发布供验签）'))


def downgrade() -> None:
    op.drop_column('users', 'github_public_key')
    op.drop_column('users', 'github_sign_key_encrypted')
    op.drop_column('users', 'github_id')
