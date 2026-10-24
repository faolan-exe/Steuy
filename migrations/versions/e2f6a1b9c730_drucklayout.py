"""drucklayout

Revision ID: e2f6a1b9c730
Revises: c4a8e2d7f915
Create Date: 2026-10-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2f6a1b9c730'
down_revision = 'c4a8e2d7f915'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'drucklayout',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('layout', sa.Integer(), server_default='1', nullable=False),
        sa.Column('akzent', sa.String(length=7), server_default='#2e7d4f', nullable=False),
        sa.Column('schrift', sa.String(length=20), server_default='sans', nullable=False),
        sa.Column('schrift_text', sa.Integer(), server_default='10', nullable=False),
        sa.Column('schrift_titel', sa.Integer(), server_default='15', nullable=False),
        sa.Column('logo_sha256', sa.String(length=64), nullable=True),
        sa.Column('logo_mime', sa.String(length=30), nullable=True),
        sa.Column('logo_prozent', sa.Integer(), server_default='100', nullable=False),
        sa.Column('zeige_absenderzeile', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('zeige_pos', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('gesamt_grau', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('zeige_fusszeile', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('zeige_bank', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('zeige_steuer', sa.Boolean(), server_default='true', nullable=False),
        sa.CheckConstraint('id = 1', name='drucklayout_nur_eine_zeile'),
        sa.CheckConstraint('layout BETWEEN 1 AND 5', name='drucklayout_layout'),
        sa.CheckConstraint('logo_prozent BETWEEN 30 AND 250', name='drucklayout_logo_prozent'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('drucklayout')
