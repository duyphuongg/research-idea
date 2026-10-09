"""nfl_performances and nfl_player_demand

Revision ID: d4f6b8c0e213
Revises: c3e5a7b9d102
Create Date: 2026-10-09 22:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4f6b8c0e213'
down_revision: Union[str, Sequence[str], None] = 'c3e5a7b9d102'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'nfl_performances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('season', sa.Integer(), nullable=False),
        sa.Column('season_type', sa.Integer(), nullable=False),
        sa.Column('week', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.String(length=20), nullable=False),
        sa.Column('game', sa.String(length=200), nullable=False),
        sa.Column('game_date', sa.DateTime(), nullable=True),
        sa.Column('athlete_id', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('position', sa.String(length=10), nullable=True),
        sa.Column('jersey', sa.String(length=5), nullable=True),
        sa.Column('team', sa.String(length=10), nullable=True),
        sa.Column('category', sa.String(length=30), nullable=False),
        sa.Column('stat_line', sa.String(length=100), nullable=False),
        sa.Column('points', sa.Float(), nullable=False),
        sa.Column('headshot_url', sa.String(length=500), nullable=True),
        sa.Column('player_url', sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('season', 'season_type', 'week', 'event_id', 'athlete_id', 'category'),
    )
    op.create_index('ix_nfl_performances_week', 'nfl_performances', ['season', 'season_type', 'week'])
    op.create_table(
        'nfl_player_demand',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('athlete_id', sa.String(length=20), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('etsy_listings', sa.Integer(), nullable=True),
        sa.Column('merch_suggestions', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('athlete_id', 'date'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('nfl_player_demand')
    op.drop_index('ix_nfl_performances_week', table_name='nfl_performances')
    op.drop_table('nfl_performances')
