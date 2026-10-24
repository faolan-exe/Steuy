"""auto mahnen

Revision ID: a7c9e1d4b256
Revises: f3b7c2d8a941
Create Date: 2026-10-24 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c9e1d4b256'
down_revision = 'f3b7c2d8a941'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('gewerbe', sa.Column('auto_mahnen', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('mahnung', sa.Column('automatisch', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade():
    op.drop_column('mahnung', 'automatisch')
    op.drop_column('gewerbe', 'auto_mahnen')
