"""Merge multiple heads

Revision ID: c739426df8e3
Revises: 7c17bdd33c02, 9c766b1a2e8c
Create Date: 2026-06-26 16:33:24.046345

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'c739426df8e3'
down_revision: Union[str, None] = ('7c17bdd33c02', '9c766b1a2e8c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
