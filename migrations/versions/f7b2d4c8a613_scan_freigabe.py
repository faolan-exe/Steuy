"""Scan-Eingang: Netzwerkfreigabe (Samba) an und aus, Passwort

Revision ID: f7b2d4c8a613
Revises: e4a7c9b1d352
Create Date: 2026-10-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7b2d4c8a613'
down_revision = 'e4a7c9b1d352'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('gewerbe', sa.Column('scan_freigabe', sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column('gewerbe', sa.Column('scan_kompatibel', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('gewerbe', sa.Column('scan_passwort', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('gewerbe', 'scan_passwort')
    op.drop_column('gewerbe', 'scan_kompatibel')
    op.drop_column('gewerbe', 'scan_freigabe')
