"""Add cancellation fields to orders

Revision ID: f1a2b3c4d5e6
Revises: eaaec2cef7b3
Create Date: 2026-08-09 16:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('cancellation_reason', sa.String(length=500), nullable=True))
    op.add_column('orders', sa.Column('cancellation_phase', sa.String(length=50), nullable=True))
    op.add_column('orders', sa.Column('cancelled_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('orders', 'cancelled_at')
    op.drop_column('orders', 'cancellation_phase')
    op.drop_column('orders', 'cancellation_reason')
