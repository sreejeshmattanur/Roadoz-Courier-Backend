"""create auth_user_profiles table

Revision ID: 7b951c8a14b3
Revises: 6a92181b8846
Create Date: 2026-06-25 13:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '7b951c8a14b3'
down_revision: Union[str, None] = '6a92181b8846'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    
    # Only create the table if it does not already exist
    if 'auth_user_profiles' not in tables:
        op.create_table(
            'auth_user_profiles',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('user_id', sa.String(length=36), nullable=False),
            sa.Column('first_name', sa.String(length=100), nullable=True),
            sa.Column('last_name', sa.String(length=100), nullable=True),
            sa.Column('phone', sa.String(length=15), nullable=True),
            sa.Column('alternate_phone', sa.String(length=15), nullable=True),
            sa.Column('date_of_birth', sa.DateTime(), nullable=True),
            sa.Column('gender', sa.String(length=20), nullable=True),
            sa.Column('address_line_1', sa.String(length=255), nullable=True),
            sa.Column('address_line_2', sa.String(length=255), nullable=True),
            sa.Column('city', sa.String(length=100), nullable=True),
            sa.Column('state', sa.String(length=100), nullable=True),
            sa.Column('pincode', sa.String(length=10), nullable=True),
            sa.Column('country', sa.String(length=100), nullable=True, server_default='India'),
            sa.Column('profile_image_url', sa.String(length=500), nullable=True),
            sa.Column('bio', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['auth_users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id')
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    
    if 'auth_user_profiles' in tables:
        op.drop_table('auth_user_profiles')
