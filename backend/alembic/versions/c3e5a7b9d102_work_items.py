"""work_items

Revision ID: c3e5a7b9d102
Revises: b7c2d4e6f801
Create Date: 2026-10-09 20:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3e5a7b9d102'
down_revision: Union[str, Sequence[str], None] = 'b7c2d4e6f801'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'work_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subject_kind', sa.String(length=10), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('note', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('subject_kind', 'subject_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('work_items')
