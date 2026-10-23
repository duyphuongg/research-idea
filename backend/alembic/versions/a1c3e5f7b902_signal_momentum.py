"""listing_signals momentum + top_share

Revision ID: a1c3e5f7b902
Revises: f6b8d0e2a435
Create Date: 2026-10-23 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1c3e5f7b902'
down_revision: Union[str, Sequence[str], None] = 'f6b8d0e2a435'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('listing_signals') as batch:
        batch.add_column(sa.Column('momentum', sa.Float(), nullable=True))
        batch.add_column(sa.Column('top_share', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('listing_signals') as batch:
        batch.drop_column('top_share')
        batch.drop_column('momentum')
