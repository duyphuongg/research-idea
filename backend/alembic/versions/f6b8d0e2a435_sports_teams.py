"""sports_teams

Revision ID: f6b8d0e2a435
Revises: e5a7c9d1f324
Create Date: 2026-10-09 23:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f6b8d0e2a435'
down_revision: Union[str, Sequence[str], None] = 'e5a7c9d1f324'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'sports_teams',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('league', sa.String(length=10), nullable=False),
        sa.Column('abbreviation', sa.String(length=10), nullable=False),
        sa.Column('full_name', sa.String(length=100), nullable=False),
        sa.Column('nickname', sa.String(length=60), nullable=False),
        sa.Column('updated_on', sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('league', 'abbreviation'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('sports_teams')
