"""drop amazon alerts

Revision ID: 3ac364acafae
Revises: 6ed06a8bb741
Create Date: 2026-10-09 11:30:47.738960

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ac364acafae'
down_revision: Union[str, Sequence[str], None] = '6ed06a8bb741'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Delete alerts of the removed Amazon rule (data only; the amazon_ranks table stays)."""
    op.execute(sa.text("DELETE FROM alerts WHERE kind = 'amazon'"))


def downgrade() -> None:
    """No-op: deleted Amazon alerts are not restored."""
