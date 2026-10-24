"""update uebersprungen

Revision ID: c4a8e2d7f915
Revises: 9b1d4e6f3a21
Create Date: 2026-10-24 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4a8e2d7f915'
down_revision = '9b1d4e6f3a21'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('gewerbe', schema=None) as batch_op:
        batch_op.add_column(sa.Column('update_uebersprungen', sa.String(length=20), nullable=True))


def downgrade():
    with op.batch_alter_table('gewerbe', schema=None) as batch_op:
        batch_op.drop_column('update_uebersprungen')
