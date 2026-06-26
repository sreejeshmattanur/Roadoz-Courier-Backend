"""add credit_amount to orders

Revision ID: 9c766b1a2e8c
Revises: 5c595aeeee89
Create Date: 2026-06-26 14:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '9c766b1a2e8c'
down_revision: Union[str, None] = '5c595aeeee89'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('credit_amount', sa.Numeric(precision=12, scale=2), nullable=True))


def downgrade() -> None:
    op.drop_column('orders', 'credit_amount')
