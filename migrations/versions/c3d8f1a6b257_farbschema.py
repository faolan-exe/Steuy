"""Farbschema je Nutzer: automatisch, hell oder dunkel

Revision ID: c3d8f1a6b257
Revises: b9e5f3a7d024
Create Date: 2026-11-12 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d8f1a6b257'
down_revision = 'b9e5f3a7d024'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('nutzer', sa.Column('farbschema', sa.String(length=6), server_default='auto', nullable=False))
    op.create_check_constraint(
        'nutzer_farbschema_gueltig', 'nutzer', "farbschema IN ('auto', 'hell', 'dunkel')"
    )


def downgrade():
    op.drop_constraint('nutzer_farbschema_gueltig', 'nutzer', type_='check')
    op.drop_column('nutzer', 'farbschema')
