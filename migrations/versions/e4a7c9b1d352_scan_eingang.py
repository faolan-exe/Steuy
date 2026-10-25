"""Scan-Eingang: Einstellung und letzter Lauf

Revision ID: e4a7c9b1d352
Revises: d1f5b8a2c764
Create Date: 2026-10-25 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e4a7c9b1d352'
down_revision = 'd1f5b8a2c764'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('gewerbe', sa.Column('scan_aktiv', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('gewerbe', sa.Column('scan_letzter_lauf', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('gewerbe', 'scan_letzter_lauf')
    op.drop_column('gewerbe', 'scan_aktiv')
