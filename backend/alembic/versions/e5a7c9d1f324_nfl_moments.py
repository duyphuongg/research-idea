"""nfl_players and nfl_moments

Revision ID: e5a7c9d1f324
Revises: d4f6b8c0e213
Create Date: 2026-10-09 23:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e5a7c9d1f324'
down_revision: Union[str, Sequence[str], None] = 'd4f6b8c0e213'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'nfl_players',
        sa.Column('athlete_id', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('first_name', sa.String(length=60), nullable=False),
        sa.Column('last_name', sa.String(length=60), nullable=False),
        sa.Column('team', sa.String(length=10), nullable=True),
        sa.Column('position', sa.String(length=10), nullable=True),
        sa.Column('jersey', sa.String(length=5), nullable=True),
        sa.Column('headshot_url', sa.String(length=500), nullable=True),
        sa.Column('updated_on', sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint('athlete_id'),
    )
    op.create_table(
        'nfl_moments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('query', sa.String(length=200), nullable=False),
        sa.Column('traffic', sa.Integer(), nullable=False),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.Column('news', sa.JSON(), nullable=False),
        sa.Column('picture_url', sa.String(length=1000), nullable=True),
        sa.Column('athlete_id', sa.String(length=20), nullable=True),
        sa.Column('team', sa.String(length=10), nullable=True),
        sa.Column('etsy_listings', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('query'),
    )
    op.create_index('ix_nfl_moments_athlete_id', 'nfl_moments', ['athlete_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_nfl_moments_athlete_id', table_name='nfl_moments')
    op.drop_table('nfl_moments')
    op.drop_table('nfl_players')
