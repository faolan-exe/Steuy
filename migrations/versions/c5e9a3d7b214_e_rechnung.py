"""E-Rechnung: Einstellung, Leitweg-ID und Ablage des XML

Revision ID: c5e9a3d7b214
Revises: b3d7f1a9c825
Create Date: 2026-10-26 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c5e9a3d7b214'
down_revision = 'b3d7f1a9c825'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('gewerbe', sa.Column('e_rechnung', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('kontakt', sa.Column('leitweg_id', sa.String(length=46), nullable=True))
    op.add_column('rechnung', sa.Column('xml_sha256', sa.String(length=64), nullable=True))


def downgrade():
    op.drop_column('rechnung', 'xml_sha256')
    op.drop_column('kontakt', 'leitweg_id')
    op.drop_column('gewerbe', 'e_rechnung')
