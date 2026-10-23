"""topic_snapshots

Revision ID: b2d4f6a8c013
Revises: a1c3e5f7b902
Create Date: 2026-10-23 11:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b2d4f6a8c013'
down_revision: Union[str, Sequence[str], None] = 'a1c3e5f7b902'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'topic_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('key', sa.String(length=200), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('aliases', sa.JSON(), nullable=False),
        sa.Column('listings', sa.Integer(), nullable=False),
        sa.Column('shops', sa.Integer(), nullable=False),
        sa.Column('rising', sa.Integer(), nullable=False),
        sa.Column('gain_7d', sa.Float(), nullable=False),
        sa.Column('prev_gain_7d', sa.Float(), nullable=True),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('product_ids', sa.JSON(), nullable=False),
        sa.Column('ip_level', sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('date', 'key'),
    )
    op.create_index('ix_topic_snapshots_date', 'topic_snapshots', ['date'])
    op.create_index('ix_topic_snapshots_key', 'topic_snapshots', ['key'])


def downgrade() -> None:
    op.drop_index('ix_topic_snapshots_key', table_name='topic_snapshots')
    op.drop_index('ix_topic_snapshots_date', table_name='topic_snapshots')
    op.drop_table('topic_snapshots')
