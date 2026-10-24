"""rundgang

Revision ID: c9e3a5f7d412
Revises: b8d2f4a6c130
Create Date: 2026-10-24 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9e3a5f7d412'
down_revision = 'b8d2f4a6c130'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('nutzer', sa.Column('erfahrung', sa.String(length=12), nullable=True))
    op.add_column('nutzer', sa.Column('kennt_steuy', sa.Boolean(), nullable=True))
    op.add_column('nutzer', sa.Column('rundgang_schritt', sa.Integer(), nullable=True))
    op.add_column(
        'nutzer',
        sa.Column('rundgang_fertig', sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_check_constraint(
        'nutzer_erfahrung', 'nutzer', "erfahrung IN ('anfaenger', 'erfahren', 'experte')"
    )


def downgrade():
    op.drop_constraint('nutzer_erfahrung', 'nutzer', type_='check')
    op.drop_column('nutzer', 'rundgang_fertig')
    op.drop_column('nutzer', 'rundgang_schritt')
    op.drop_column('nutzer', 'kennt_steuy')
    op.drop_column('nutzer', 'erfahrung')
