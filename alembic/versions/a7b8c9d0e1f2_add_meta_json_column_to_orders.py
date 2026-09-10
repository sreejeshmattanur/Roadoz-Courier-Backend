"""Add meta JSON column to orders

Revision ID: a7b8c9d0e1f2
Revises: eaaec2cef7b3
Create Date: 2026-08-09 13:39:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'eaaec2cef7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('meta', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('orders', 'meta')
