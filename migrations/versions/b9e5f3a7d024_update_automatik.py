"""Update: automatische Suche abschaltbar, gefundene Version merken

Revision ID: b9e5f3a7d024
Revises: a8d4e2f6c913
Create Date: 2026-11-11 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b9e5f3a7d024'
down_revision = 'a8d4e2f6c913'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('gewerbe', sa.Column('update_auto_suchen', sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column('gewerbe', sa.Column('update_gesucht_am', sa.DateTime(timezone=True), nullable=True))
    op.add_column('gewerbe', sa.Column('update_verfuegbar', sa.String(length=20), nullable=True))


def downgrade():
    op.drop_column('gewerbe', 'update_verfuegbar')
    op.drop_column('gewerbe', 'update_gesucht_am')
    op.drop_column('gewerbe', 'update_auto_suchen')
