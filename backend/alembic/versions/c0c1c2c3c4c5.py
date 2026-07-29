"""fix: recreate tables dropped by autogenerate in 20efaf9a57ca

Revision ID: c0c1c2c3c4c5
Revises: 20efaf9a57ca
Create Date: 2026-07-29 15:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c0c1c2c3c4c5'
down_revision: Union[str, None] = '20efaf9a57ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
    op.execute('CREATE INDEX IF NOT EXISTS idx_file_metadata_owner ON file_metadata (owner_type, owner_id)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_group_invitations_group ON group_invitations (group_id)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_group_invitations_invitee ON group_invitations (invitee_id, status)')


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS idx_group_invitations_invitee')
    op.execute('DROP INDEX IF EXISTS idx_group_invitations_group')
    op.execute('DROP INDEX IF EXISTS idx_file_metadata_owner')
    op.drop_table('structured_records')
    op.drop_table('agent_workspace')
    op.drop_table('agent_alarms')
