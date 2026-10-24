"""firmenname neben logo

Revision ID: f3b7c2d8a941
Revises: e2f6a1b9c730
Create Date: 2026-10-24 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3b7c2d8a941'
down_revision = 'e2f6a1b9c730'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'drucklayout',
        sa.Column('zeige_firmenname', sa.Boolean(), server_default='true', nullable=False),
    )


def downgrade():
    op.drop_column('drucklayout', 'zeige_firmenname')
