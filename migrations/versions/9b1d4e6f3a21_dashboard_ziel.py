"""dashboard ziel

Revision ID: 9b1d4e6f3a21
Revises: 7c3e91a4b2d8
Create Date: 2026-10-24 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9b1d4e6f3a21'
down_revision = '7c3e91a4b2d8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('gewerbe', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ziel_art', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('ziel_wert', sa.BigInteger(), nullable=True))
        batch_op.create_check_constraint(
            'gewerbe_ziel_art', "ziel_art IN ('auftraege', 'umsatz', 'gewinn')"
        )
        batch_op.create_check_constraint(
            'gewerbe_ziel_wert', "(ziel_art IS NULL) = (ziel_wert IS NULL) AND (ziel_wert IS NULL OR ziel_wert > 0)"
        )


def downgrade():
    with op.batch_alter_table('gewerbe', schema=None) as batch_op:
        batch_op.drop_constraint('gewerbe_ziel_wert', type_='check')
        batch_op.drop_constraint('gewerbe_ziel_art', type_='check')
        batch_op.drop_column('ziel_wert')
        batch_op.drop_column('ziel_art')
