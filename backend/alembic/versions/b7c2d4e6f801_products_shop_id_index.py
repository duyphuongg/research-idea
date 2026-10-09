"""products.shop_id index

Revision ID: b7c2d4e6f801
Revises: feaded8cf8fb
Create Date: 2026-10-09 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b7c2d4e6f801'
down_revision: Union[str, Sequence[str], None] = 'feaded8cf8fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.create_index('ix_products_shop_id', ['shop_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_index('ix_products_shop_id')
