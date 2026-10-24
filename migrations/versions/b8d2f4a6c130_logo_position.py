"""logo position

Revision ID: b8d2f4a6c130
Revises: a7c9e1d4b256
Create Date: 2026-10-24 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8d2f4a6c130'
down_revision = 'a7c9e1d4b256'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'drucklayout',
        sa.Column('logo_position', sa.String(length=10), server_default='auto', nullable=False),
    )
    op.create_check_constraint(
        'drucklayout_logo_position',
        'drucklayout',
        "logo_position IN ('auto', 'links', 'mitte', 'rechts')",
    )


def downgrade():
    op.drop_constraint('drucklayout_logo_position', 'drucklayout', type_='check')
    op.drop_column('drucklayout', 'logo_position')
