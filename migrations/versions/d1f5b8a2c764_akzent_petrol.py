"""Standard-Akzentfarbe des Drucklayouts: Petrol

Revision ID: d1f5b8a2c764
Revises: c9e3a5f7d412
Create Date: 2026-10-24 20:40:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'd1f5b8a2c764'
down_revision = 'c9e3a5f7d412'
branch_labels = None
depends_on = None


def upgrade():
    # Nur der Standard für neue Zeilen. Gespeicherte Farben bleiben, wie sie sind.
    op.alter_column("drucklayout", "akzent", server_default="#0f7c80")


def downgrade():
    op.alter_column("drucklayout", "akzent", server_default="#2e7d4f")
